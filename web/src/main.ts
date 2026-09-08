import "./styles.css";
import {
  FAVOURITES_STORAGE_KEY,
  LOCATION_STORAGE_KEY,
  buildPageDescriptors,
  cataloguePagePosition,
  currentFavouriteEntries,
  descriptorPosition,
  favouriteItemPosition,
  hasFavouriteProduct,
  parseFavouriteIds,
  toggleFavouriteProducts,
  type PageDescriptor,
} from "./favourites";
import {
  COLOUR_STORAGE_KEY,
  DEFAULT_COLOURS,
  PERSONAL_SYNC_PENDING_KEY,
  durableState,
  isDefaultColours,
  parseColours,
  type ColourKey,
  type Colours,
  type RemotePersonalState,
} from "./personal-state";
import { historyPlotValues, type HistoryPoint } from "./history";

type ProductView = {
  product_id: string;
  name: string;
  variant: string | null;
  size: string | null;
  image_key: string | null;
};

type Offer = {
  regular_price_cents: number | null;
  special_price_cents: number | null;
  saving_cents: number | null;
  offer_text: string;
  price_unit: string | null;
  product_ids: string[];
};

type CatalogueItem = {
  type: "family" | "product" | "uncertain";
  id: string;
  name: string;
  discount_percent: number | null;
  products: ProductView[];
  offers: Offer[];
};

type PageData = {
  page: number;
  discount_group: string;
  discount_group_label: string;
  items: CatalogueItem[];
};
type DiscountGroupSummary = {
  id: string;
  label: string;
  item_count: number;
  start_page: number | null;
  page_count: number;
};
type Manifest = {
  generated_at: string;
  page_size: number;
  page_count: number;
  pages: string[];
  search_index: string;
  discount_groups: DiscountGroupSummary[];
  ordering: {
    mode: "deterministic_random";
    seed: number;
  };
};
type SearchEntry = {
  id: string;
  name: string;
  details: string[];
  image_key: string | null;
  product_ids: string[];
  search_text: string;
  page: number;
};
type SearchIndex = { items: SearchEntry[] };

const pagesElement = document.querySelector<HTMLDivElement>("#pages")!;
const statusElement = document.querySelector<HTMLParagraphElement>("#status")!;
const pageSelect = document.querySelector<HTMLSelectElement>("#page-select")!;
const pageLabel = document.querySelector<HTMLSpanElement>("#page-label")!;
const discountGroupLabel = document.querySelector<HTMLSpanElement>("#discount-group-label")!;
const previousButton = document.querySelector<HTMLButtonElement>("#previous")!;
const nextButton = document.querySelector<HTMLButtonElement>("#next")!;
const firstButton = document.querySelector<HTMLButtonElement>("#first")!;
const productDialog = document.querySelector<HTMLDialogElement>("#product-dialog")!;
const productDialogClose = document.querySelector<HTMLButtonElement>("#product-dialog-close")!;
const productDialogTitle = document.querySelector<HTMLHeadingElement>("#product-dialog-title")!;
const productDialogContent = document.querySelector<HTMLDivElement>("#product-dialog-content")!;
const searchOpen = document.querySelector<HTMLButtonElement>("#search-open")!;
const searchDialog = document.querySelector<HTMLDialogElement>("#search-dialog")!;
const searchClose = document.querySelector<HTMLButtonElement>("#search-close")!;
const searchInput = document.querySelector<HTMLInputElement>("#search-input")!;
const searchSummary = document.querySelector<HTMLParagraphElement>("#search-summary")!;
const searchResults = document.querySelector<HTMLDivElement>("#search-results")!;
const settingsOpen = document.querySelector<HTMLButtonElement>("#settings-open")!;
const settingsDialog = document.querySelector<HTMLDialogElement>("#settings-dialog")!;
const settingsClose = document.querySelector<HTMLButtonElement>("#settings-close")!;
const settingsDefault = document.querySelector<HTMLButtonElement>("#settings-default")!;
const placeholderUrl = "./placeholder.svg";
const SEARCH_INITIAL_RESULTS = 10;
const SEARCH_MORE_RESULTS = 20;
const SEARCH_DEBOUNCE_MS = 500;
const colourControls: Record<ColourKey, { input: HTMLInputElement; property: string }> = {
  page: {
    input: document.querySelector<HTMLInputElement>("#colour-page")!,
    property: "--custom-page-background",
  },
  price: {
    input: document.querySelector<HTMLInputElement>("#colour-price")!,
    property: "--custom-price-circle",
  },
  saving: {
    input: document.querySelector<HTMLInputElement>("#colour-saving")!,
    property: "--custom-saving-label",
  },
  card: {
    input: document.querySelector<HTMLInputElement>("#colour-card")!,
    property: "--custom-product-card",
  },
};
const loaded = new Set<number>();
const loading = new Set<number>();
const pageData = new Map<number, PageData>();
const pageRequests = new Map<number, Promise<PageData>>();
let manifest: Manifest;
let pageDescriptors: PageDescriptor[] = [];
let pageObserver: IntersectionObserver | null = null;
let pageGeneration = 0;
let rebuildingPageModel = false;
let favouriteProductIds = new Set<string>();
let favouriteItems = new Map<string, CatalogueItem>();
let searchIndex: SearchIndex | null = null;
let searchIndexRequest: Promise<SearchIndex> | null = null;
let currentPage = 1;
let scrollTimer = 0;
let dialogCloseTimer = 0;
let searchDebounceTimer = 0;
let searchMatches: SearchEntry[] = [];
let visibleSearchResultCount = 0;
let dialogOpener: HTMLElement | null = null;
let dialogItem: CatalogueItem | null = null;
let dialogInitialFavourite = false;
let personalHistoryEnabled = false;
let personalSyncTimer = 0;
let personalSyncRevision = 0;
let personalSyncInFlight: Promise<void> | null = null;
let personalStateMessage = "";
let personalReconcileRetries = 0;

function applyColours(colours: Colours): void {
  (Object.keys(DEFAULT_COLOURS) as ColourKey[]).forEach((key) => {
    colourControls[key].input.value = colours[key];
    document.documentElement.style.setProperty(colourControls[key].property, colours[key]);
  });
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute("content", colours.page);
}

function loadColours(): Colours {
  return parseColours(localStorage.getItem(COLOUR_STORAGE_KEY));
}

function saveSelectedColours(): void {
  const colours = Object.fromEntries(
    (Object.keys(DEFAULT_COLOURS) as ColourKey[]).map((key) => [key, colourControls[key].input.value]),
  ) as Colours;
  localStorage.setItem(COLOUR_STORAGE_KEY, JSON.stringify(colours));
  applyColours(colours);
  markPersonalSyncPending(700);
}

function currentDurableState() {
  return durableState(favouriteProductIds, loadColours());
}

function markPersonalSyncPending(delay = 0): void {
  localStorage.setItem(PERSONAL_SYNC_PENDING_KEY, "1");
  personalSyncRevision += 1;
  window.clearTimeout(personalSyncTimer);
  personalSyncTimer = window.setTimeout(() => void pushPersonalState(), delay);
}

async function pushPersonalState(): Promise<void> {
  if (personalSyncInFlight) return personalSyncInFlight;
  const revision = personalSyncRevision;
  personalSyncInFlight = (async () => {
    try {
      const response = await fetch("/api/profile/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentDurableState()),
      });
      if (!response.ok) throw new Error(`personal state returned ${response.status}`);
      const state = (await response.json()) as RemotePersonalState;
      personalHistoryEnabled = state.history_enabled;
      if (revision === personalSyncRevision) {
        localStorage.removeItem(PERSONAL_SYNC_PENDING_KEY);
      }
    } catch {
      window.setTimeout(() => {
        if (localStorage.getItem(PERSONAL_SYNC_PENDING_KEY)) void pushPersonalState();
      }, 15_000);
    } finally {
      personalSyncInFlight = null;
      if (localStorage.getItem(PERSONAL_SYNC_PENDING_KEY) && revision !== personalSyncRevision) {
        window.clearTimeout(personalSyncTimer);
        personalSyncTimer = window.setTimeout(() => void pushPersonalState(), 250);
      }
    }
  })();
  return personalSyncInFlight;
}

async function replaceWithRemoteState(state: RemotePersonalState): Promise<void> {
  favouriteProductIds = new Set(parseFavouriteIds(JSON.stringify(state.favourites)));
  localStorage.setItem(FAVOURITES_STORAGE_KEY, JSON.stringify([...favouriteProductIds]));
  localStorage.setItem(COLOUR_STORAGE_KEY, JSON.stringify(state.customizations));
  applyColours(parseColours(JSON.stringify(state.customizations)));
  personalHistoryEnabled = state.history_enabled;
  localStorage.removeItem(PERSONAL_SYNC_PENDING_KEY);
  if (typeof manifest !== "undefined") {
    try {
      await refreshPageModel(pageDescriptors[currentPage - 1]?.key ?? null);
    } catch {
      showPersonalStateMessage("Personal settings were saved; the catalogue view will refresh on reload.");
    }
  }
}

function captureRestoreCode(): string | null {
  const parameters = new URLSearchParams(location.hash.startsWith("#") ? location.hash.slice(1) : "");
  const syncCode = parameters.get("restore");
  if (!syncCode) return null;
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  return syncCode;
}

function showPersonalStateMessage(message: string): void {
  personalStateMessage = message;
  if (typeof manifest !== "undefined") {
    statusElement.textContent = `Updated ${new Date(manifest.generated_at).toLocaleDateString()} · ${message}`;
  }
}

async function requestRestoredState(syncCode: string): Promise<RemotePersonalState | null> {
  try {
    const response = await fetch("/api/profile/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sync_code: syncCode }),
    });
    if (!response.ok) throw new Error("restore failed");
    return await response.json() as RemotePersonalState;
  } catch {
    return null;
  }
}

async function applyRestoreResult(request: Promise<RemotePersonalState | null>): Promise<void> {
  const state = await request;
  if (state) {
    await replaceWithRemoteState(state);
    showPersonalStateMessage("Personal settings restored.");
  } else {
    showPersonalStateMessage("Sync Code could not be restored; local settings were kept.");
  }
}

async function reconcilePersonalState(): Promise<void> {
  try {
    if (localStorage.getItem(PERSONAL_SYNC_PENDING_KEY)) {
      await pushPersonalState();
      return;
    }
    const response = await fetch("/api/profile/state", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("personal state unavailable");
    personalReconcileRetries = 0;
    const remote = await response.json() as RemotePersonalState;
    if (remote.has_profile) {
      await replaceWithRemoteState(remote);
    } else {
      const local = currentDurableState();
      if (local.favourites.length || !isDefaultColours(local.customizations)) {
        markPersonalSyncPending();
      }
    }
  } catch {
    // Personal state is optional; local catalogue state remains fully usable.
    if (personalReconcileRetries < 3) {
      personalReconcileRetries += 1;
      window.setTimeout(() => void reconcilePersonalState(), 15_000 * personalReconcileRetries);
    }
  }
}

function money(cents: number | null): string {
  if (cents === null) return "—";
  const dollars = Math.floor(cents / 100);
  const remainder = cents % 100;
  return remainder ? `$${dollars}.${remainder.toString().padStart(2, "0")}` : `$${dollars}`;
}

function imageUrl(key: string | null): string {
  if (!key) return placeholderUrl;
  return `/images/${key.split("/").map(encodeURIComponent).join("/")}`;
}

function makeImage(product: ProductView): HTMLImageElement {
  const image = document.createElement("img");
  image.src = imageUrl(product.image_key);
  image.alt = product.name;
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    if (!image.src.endsWith("placeholder.svg")) image.src = placeholderUrl;
  });
  return image;
}

function priceBadge(offer: Offer): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "price-block";
  const circle = document.createElement("div");
  circle.className = "price-badge";
  circle.textContent = money(offer.special_price_cents);
  wrapper.append(circle);
  const normalizedUnit = offer.price_unit?.toLocaleLowerCase() ?? "";
  const compactUnit = normalizedUnit.includes("approx") ? "EACH APX" : null;
  if (compactUnit) {
    const unit = document.createElement("span");
    unit.className = "price-unit-label";
    unit.textContent = compactUnit;
    unit.setAttribute("aria-label", offer.price_unit || compactUnit);
    wrapper.append(unit);
  }
  if (offer.saving_cents !== null) {
    const saving = document.createElement("span");
    saving.className = "saving-label";
    saving.textContent = `SAVE ${money(offer.saving_cents)}`;
    wrapper.append(saving);
  }
  return wrapper;
}

function promotionProductLabel(product: ProductView): string {
  const label = product.variant || product.name;
  return product.size && !label.toLowerCase().includes(product.size.toLowerCase())
    ? `${label} (${product.size})`
    : label;
}

function itemProductIds(item: CatalogueItem): string[] {
  return item.products.map((product) => product.product_id);
}

function isFavourite(item: CatalogueItem): boolean {
  return hasFavouriteProduct(itemProductIds(item), favouriteProductIds);
}

function updateFavouriteButton(button: HTMLButtonElement, item: CatalogueItem): void {
  const active = isFavourite(item);
  button.classList.toggle("is-favourite", active);
  button.textContent = active ? "★" : "☆";
  button.setAttribute("aria-pressed", String(active));
  button.setAttribute("aria-label", `${active ? "Remove" : "Add"} ${item.name} ${active ? "from" : "to"} favourites`);
}

function makeFavouriteButton(item: CatalogueItem): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = "favourite-toggle";
  button.type = "button";
  updateFavouriteButton(button, item);
  button.addEventListener("click", () => {
    favouriteProductIds = new Set(
      toggleFavouriteProducts(favouriteProductIds, itemProductIds(item)),
    );
    localStorage.setItem(FAVOURITES_STORAGE_KEY, JSON.stringify([...favouriteProductIds]));
    updateFavouriteButton(button, item);
    markPersonalSyncPending();
  });
  return button;
}

function historyPointLabel(point: HistoryPoint, value: number | null): string {
  if (!point.available) return `${point.date}: unavailable`;
  if (point.is_special === false) return `${point.date}: no special, 0%`;
  return value === null ? `${point.date}: special, discount unavailable` : `${point.date}: ${value}% off`;
}

function renderHistoryGraph(container: HTMLElement, points: HistoryPoint[]): void {
  container.replaceChildren();
  if (!points.length) {
    container.textContent = "No recorded history for this product yet.";
    return;
  }
  const values = historyPlotValues(points);
  const width = 560;
  const height = 220;
  const padding = 34;
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;
  const x = (index: number) => padding + (points.length === 1 ? usableWidth / 2 : index * usableWidth / (points.length - 1));
  const y = (value: number) => height - padding - Math.max(0, Math.min(100, value)) * usableHeight / 100;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Weekly discount history line graph");
  svg.classList.add("history-chart");
  const baseline = document.createElementNS(svg.namespaceURI, "line");
  baseline.setAttribute("x1", String(padding));
  baseline.setAttribute("x2", String(width - padding));
  baseline.setAttribute("y1", String(y(0)));
  baseline.setAttribute("y2", String(y(0)));
  baseline.classList.add("history-baseline");
  svg.append(baseline);
  for (let index = 1; index < values.length; index += 1) {
    const previous = values[index - 1];
    const current = values[index];
    if (previous === null || current === null) continue;
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", String(x(index - 1)));
    line.setAttribute("y1", String(y(previous)));
    line.setAttribute("x2", String(x(index)));
    line.setAttribute("y2", String(y(current)));
    line.classList.add("history-line");
    svg.append(line);
  }
  values.forEach((value, index) => {
    if (value === null) return;
    const circle = document.createElementNS(svg.namespaceURI, "circle");
    circle.setAttribute("cx", String(x(index)));
    circle.setAttribute("cy", String(y(value)));
    circle.setAttribute("r", "7");
    circle.classList.add("history-point");
    const title = document.createElementNS(svg.namespaceURI, "title");
    title.textContent = historyPointLabel(points[index], value);
    circle.append(title);
    svg.append(circle);
  });
  const list = document.createElement("ul");
  list.className = "history-point-list";
  points.forEach((point, index) => {
    const row = document.createElement("li");
    row.textContent = historyPointLabel(point, values[index]);
    list.append(row);
  });
  container.append(svg, list);
}

function productHistorySection(item: CatalogueItem): HTMLElement {
  const section = document.createElement("section");
  section.className = "product-history";
  const heading = document.createElement("h3");
  heading.textContent = "Discount history";
  const selector = document.createElement("select");
  selector.setAttribute("aria-label", "Product variant for discount history");
  item.products.forEach((product) => selector.add(new Option(promotionProductLabel(product), product.product_id)));
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Show discount history";
  const output = document.createElement("div");
  output.className = "product-history-output";
  button.addEventListener("click", async () => {
    button.disabled = true;
    output.textContent = "Loading history…";
    try {
      const response = await fetch(`/api/history/${encodeURIComponent(selector.value)}`);
      if (!response.ok) throw new Error(`history returned ${response.status}`);
      const result = await response.json() as { points: HistoryPoint[] };
      renderHistoryGraph(output, result.points);
    } catch {
      output.textContent = "Discount history is temporarily unavailable.";
    } finally {
      button.disabled = false;
    }
  });
  section.append(heading);
  if (item.products.length > 1) section.append(selector);
  section.append(button, output);
  return section;
}

function populateProductDialog(item: CatalogueItem): void {
  productDialogTitle.textContent = item.name;
  const gallery = document.createElement("div");
  gallery.className = `product-dialog-gallery product-dialog-gallery--${Math.min(item.products.length, 3)}`;
  item.products.forEach((product) => {
    const figure = document.createElement("figure");
    const image = makeImage(product);
    image.loading = "eager";
    const caption = document.createElement("figcaption");
    const productName = document.createElement("strong");
    productName.textContent = product.variant || product.name;
    caption.append(productName);
    if (product.size) {
      const size = document.createElement("span");
      size.textContent = product.size;
      caption.append(size);
    }
    figure.append(image, caption);
    gallery.append(figure);
  });

  const promotions = document.createElement("section");
  promotions.className = "product-dialog-promotions";
  promotions.setAttribute("aria-label", "Current promotions");
  item.offers.forEach((offer, index) => {
    const promotion = document.createElement("article");
    promotion.className = "product-dialog-promotion";
    if (index === 0) promotion.classList.add("has-favourite-toggle");
    if (item.offers.length > 1) {
      const label = document.createElement("h3");
      label.textContent = `Promotion ${index + 1}`;
      promotion.append(label);
    }
    const price = document.createElement("div");
    price.className = "product-dialog-price";
    price.append(priceBadge(offer));
    const details = document.createElement("div");
    details.className = "product-dialog-offer-details";
    if (offer.regular_price_cents !== null) {
      const was = document.createElement("p");
      was.textContent = `was ${money(offer.regular_price_cents)}`;
      details.append(was);
    }
    if (offer.offer_text) {
      const offerText = document.createElement("p");
      offerText.className = "product-dialog-offer-text";
      offerText.textContent = offer.offer_text;
      details.append(offerText);
    }
    price.append(details);
    if (index === 0) price.append(makeFavouriteButton(item));
    promotion.append(price);

    if (item.offers.length > 1 || item.products.length > 1) {
      const appliesTo = document.createElement("p");
      appliesTo.className = "product-dialog-applies";
      const products = offer.product_ids
        .map((productId) => item.products.find((product) => product.product_id === productId))
        .filter((product): product is ProductView => Boolean(product))
        .map(promotionProductLabel);
      appliesTo.textContent = `Applies to: ${products.length ? products.join(" · ") : "listed products"}`;
      promotion.append(appliesTo);
    }
    promotions.append(promotion);
  });

  productDialogContent.replaceChildren(gallery, promotions);
  if (personalHistoryEnabled) productDialogContent.append(productHistorySection(item));
}

function openProductDialog(item: CatalogueItem, opener: HTMLElement): void {
  window.clearTimeout(dialogCloseTimer);
  productDialog.classList.remove("is-closing");
  populateProductDialog(item);
  dialogOpener = opener;
  dialogItem = item;
  dialogInitialFavourite = isFavourite(item);
  productDialog.showModal();
  productDialogClose.focus();
}

function closeProductDialog(): void {
  if (!productDialog.open || productDialog.classList.contains("is-closing")) return;
  productDialog.classList.add("is-closing");
  dialogCloseTimer = window.setTimeout(() => productDialog.close(), 160);
}

function renderCard(item: CatalogueItem): HTMLElement {
  const card = document.createElement("article");
  card.className = `product-card product-card--${item.type}`;
  const visual = document.createElement("div");
  visual.className = "product-visual";
  const images = document.createElement("div");
  images.className = "product-images";
  const imageTrigger = document.createElement("button");
  imageTrigger.className = "product-image-trigger";
  imageTrigger.type = "button";
  imageTrigger.setAttribute("aria-label", `View details for ${item.name}`);
  item.products.slice(0, 3).forEach((product) => imageTrigger.append(makeImage(product)));
  imageTrigger.addEventListener("click", () => openProductDialog(item, imageTrigger));
  images.append(imageTrigger);
  const priceBlocks = document.createElement("div");
  priceBlocks.className = "price-blocks";
  item.offers.forEach((offer) => priceBlocks.append(priceBadge(offer)));
  visual.append(images, priceBlocks);
  card.append(visual);

  const detail = document.createElement("div");
  detail.className = "product-detail";
  const heading = document.createElement("h2");
  const nameTrigger = document.createElement("button");
  nameTrigger.className = "product-name-trigger";
  nameTrigger.type = "button";
  nameTrigger.textContent = item.name;
  nameTrigger.setAttribute("aria-label", `View details for ${item.name}`);
  nameTrigger.addEventListener("click", () => openProductDialog(item, nameTrigger));
  heading.append(nameTrigger);
  detail.append(heading);
  if (item.products.length > 1) {
    const variants = document.createElement("p");
    variants.className = "variants";
    variants.textContent = item.products.map((product) => product.variant).filter(Boolean).join(" · ");
    detail.append(variants);
  }
  if (item.offers[0].regular_price_cents !== null) {
    const was = document.createElement("p");
    was.className = "was-price";
    was.textContent = `was ${money(item.offers[0].regular_price_cents)}`;
    detail.append(was);
  }
  if (item.type === "uncertain") {
    const review = document.createElement("span");
    review.className = "review-label";
    review.textContent = "Review grouping";
    detail.append(review);
  }
  card.append(detail);
  return card;
}

async function getPageData(index: number): Promise<PageData> {
  const cached = pageData.get(index);
  if (cached) return cached;
  const pending = pageRequests.get(index);
  if (pending) return pending;
  const request = (async () => {
    const response = await fetch(manifest.pages[index - 1]);
    if (!response.ok) throw new Error(`page ${index} returned ${response.status}`);
    const data = (await response.json()) as PageData;
    pageData.set(index, data);
    return data;
  })();
  pageRequests.set(index, request);
  try {
    return await request;
  } finally {
    pageRequests.delete(index);
  }
}

async function loadPage(index: number): Promise<void> {
  const descriptor = pageDescriptors[index - 1];
  if (!descriptor || loaded.has(index) || loading.has(index)) return;
  const generation = pageGeneration;
  loading.add(index);
  const shell = document.querySelector<HTMLElement>(`[data-page="${index}"]`)!;
  try {
    let items: CatalogueItem[];
    if (descriptor.kind === "favourite") {
      items = descriptor.itemIds
        .map((itemId) => favouriteItems.get(itemId))
        .filter((item): item is CatalogueItem => Boolean(item));
    } else {
      const data = await getPageData(descriptor.sourcePage);
      items = data.items.filter((item) => !isFavourite(item));
    }
    if (generation !== pageGeneration) return;
    const grid = document.createElement("div");
    grid.className = "product-grid";
    items.forEach((item) => grid.append(renderCard(item)));
    if (!items.length) {
      grid.classList.add("product-grid--empty");
      const message = document.createElement("p");
      message.textContent = "All specials from this page are in Favourite.";
      grid.append(message);
    }
    shell.replaceChildren(grid);
    loaded.add(index);
  } catch (error) {
    if (generation !== pageGeneration) return;
    shell.textContent = "This page could not be loaded.";
    statusElement.textContent = error instanceof Error ? error.message : "Page load failed";
  } finally {
    if (generation === pageGeneration) loading.delete(index);
  }
}

function unloadDistantPages(): void {
  loaded.forEach((page) => {
    if (Math.abs(page - currentPage) > 1) {
      const shell = document.querySelector<HTMLElement>(`[data-page="${page}"]`);
      shell?.replaceChildren();
      loaded.delete(page);
      const descriptor = pageDescriptors[page - 1];
      if (descriptor?.kind === "catalogue") pageData.delete(descriptor.sourcePage);
    }
  });
}

function groupForSourcePage(page: number): DiscountGroupSummary | undefined {
  return manifest.discount_groups.find((group) =>
    group.start_page !== null
    && page >= group.start_page
    && page < group.start_page + group.page_count
  );
}

function updateControls(): void {
  const descriptor = pageDescriptors[currentPage - 1];
  if (!descriptor) return;
  pageSelect.value = String(currentPage);
  pageLabel.textContent = `Page ${currentPage} of ${pageDescriptors.length}`;
  discountGroupLabel.textContent = descriptor.kind === "favourite"
    ? "Favourite"
    : groupForSourcePage(descriptor.sourcePage)?.label ?? "Specials";
  previousButton.disabled = currentPage === 1;
  firstButton.disabled = currentPage === 1;
  nextButton.disabled = currentPage === pageDescriptors.length;
  localStorage.setItem(LOCATION_STORAGE_KEY, descriptor.key);
  void loadPage(currentPage - 1);
  void loadPage(currentPage);
  void loadPage(currentPage + 1);
  unloadDistantPages();
}

function goToPage(page: number, behavior: ScrollBehavior = "smooth"): void {
  const target = Math.max(1, Math.min(pageDescriptors.length, page));
  document.querySelector<HTMLElement>(`[data-page="${target}"]`)?.scrollIntoView({ behavior, inline: "start" });
}

async function resolveFavouriteItems(): Promise<Map<string, CatalogueItem>> {
  if (!favouriteProductIds.size) return new Map();
  const index = await loadSearchIndex();
  const entries = currentFavouriteEntries(index.items, favouriteProductIds);
  const entryIdsByPage = new Map<number, Set<string>>();
  entries.forEach((entry) => {
    const ids = entryIdsByPage.get(entry.page) ?? new Set<string>();
    ids.add(entry.id);
    entryIdsByPage.set(entry.page, ids);
  });

  const resolved = new Map<string, CatalogueItem>();
  const sourcePages = [...entryIdsByPage.keys()].sort((left, right) => left - right);
  const dataPages = await Promise.all(sourcePages.map((page) => getPageData(page)));
  dataPages.forEach((data) => {
    const currentIds = entryIdsByPage.get(data.page) ?? new Set<string>();
    data.items.forEach((item) => {
      if (currentIds.has(item.id) && isFavourite(item)) resolved.set(item.id, item);
    });
  });
  return resolved;
}

function createPageShells(): void {
  pageObserver?.disconnect();
  pageGeneration += 1;
  loaded.clear();
  loading.clear();
  pagesElement.replaceChildren();
  pageSelect.replaceChildren();
  pageDescriptors.forEach((descriptor, index) => {
    const page = index + 1;
    const shell = document.createElement("section");
    shell.className = "catalogue-page";
    shell.dataset.page = String(page);
    shell.setAttribute(
      "aria-label",
      descriptor.kind === "favourite"
        ? `Favourite catalogue page ${page}`
        : `Catalogue page ${descriptor.sourcePage}`,
    );
    pagesElement.append(shell);
    pageSelect.add(new Option(String(page), String(page)));
  });
}

function observePageShells(): void {
  pageObserver = new IntersectionObserver(
    (entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) void loadPage(Number((entry.target as HTMLElement).dataset.page));
    }),
    { root: pagesElement, rootMargin: "0px 100%", threshold: 0.01 },
  );
  document.querySelectorAll<HTMLElement>(".catalogue-page").forEach((page) => pageObserver?.observe(page));
}

async function refreshPageModel(preferredKey: string | null): Promise<void> {
  rebuildingPageModel = true;
  try {
    favouriteItems = await resolveFavouriteItems();
    pageDescriptors = buildPageDescriptors(
      [...favouriteItems.keys()],
      manifest.page_count,
      manifest.page_size,
    );
    createPageShells();
    const targetPage = descriptorPosition(pageDescriptors, preferredKey) ?? 1;
    currentPage = targetPage;
    await Promise.all([loadPage(targetPage - 1), loadPage(targetPage), loadPage(targetPage + 1)]);
    currentPage = targetPage;
    goToPage(targetPage, "auto");
    updateControls();
    observePageShells();
  } finally {
    rebuildingPageModel = false;
  }
}

async function loadSearchIndex(): Promise<SearchIndex> {
  if (searchIndex) return searchIndex;
  if (searchIndexRequest) return searchIndexRequest;
  searchIndexRequest = (async () => {
    const response = await fetch(manifest.search_index);
    if (!response.ok) throw new Error(`Search index returned ${response.status}`);
    return (await response.json()) as SearchIndex;
  })();
  try {
    searchIndex = await searchIndexRequest;
    return searchIndex;
  } finally {
    searchIndexRequest = null;
  }
}

function closeSearch(): void {
  window.clearTimeout(searchDebounceTimer);
  searchDebounceTimer = 0;
  if (searchDialog.open) searchDialog.close();
}

async function selectSearchResult(entry: SearchEntry, opener: HTMLButtonElement): Promise<void> {
  opener.disabled = true;
  searchSummary.textContent = "Loading product…";
  try {
    const data = await getPageData(entry.page);
    const item = data.items.find((candidate) => candidate.id === entry.id);
    if (!item) throw new Error("Product is no longer on this catalogue page");
    closeSearch();
    currentPage = (
      isFavourite(item)
        ? favouriteItemPosition(pageDescriptors, item.id)
        : cataloguePagePosition(pageDescriptors, entry.page)
    ) ?? currentPage;
    goToPage(currentPage, "auto");
    updateControls();
    openProductDialog(item, searchOpen);
  } catch (error) {
    opener.disabled = false;
    searchSummary.textContent = error instanceof Error ? error.message : "Product could not be loaded";
  }
}

function makeSearchResult(entry: SearchEntry): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = "search-result";
  button.type = "button";
  const image = document.createElement("img");
  image.className = "search-result-image";
  image.src = imageUrl(entry.image_key);
  image.alt = "";
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    if (!image.src.endsWith("placeholder.svg")) image.src = placeholderUrl;
  });
  const text = document.createElement("div");
  text.className = "search-result-text";
  const name = document.createElement("strong");
  name.textContent = entry.name;
  text.append(name);
  if (entry.details.length) {
    const details = document.createElement("span");
    details.textContent = entry.details.join(" · ");
    text.append(details);
  }
  button.append(image, text);
  button.addEventListener("click", () => void selectSearchResult(entry, button));
  return button;
}

function appendSearchResults(count: number): void {
  const nextCount = Math.min(visibleSearchResultCount + count, searchMatches.length);
  searchMatches
    .slice(visibleSearchResultCount, nextCount)
    .forEach((entry) => searchResults.append(makeSearchResult(entry)));
  visibleSearchResultCount = nextCount;
  searchSummary.textContent = `${searchMatches.length} result${searchMatches.length === 1 ? "" : "s"}${searchMatches.length > visibleSearchResultCount ? `; showing first ${visibleSearchResultCount}` : ""}.`;

  if (visibleSearchResultCount < searchMatches.length) {
    const more = document.createElement("button");
    more.className = "search-more";
    more.type = "button";
    more.textContent = "Search more";
    more.setAttribute("aria-label", `Show up to ${SEARCH_MORE_RESULTS} more search results`);
    more.addEventListener("click", () => {
      more.remove();
      appendSearchResults(SEARCH_MORE_RESULTS);
    });
    searchResults.append(more);
  }
}

function renderSearchResults(): void {
  const query = searchInput.value.trim().toLocaleLowerCase();
  searchResults.replaceChildren();
  searchMatches = [];
  visibleSearchResultCount = 0;
  if (!query) {
    searchSummary.textContent = "Type a product name to search.";
    return;
  }
  if (!searchIndex) return;
  const terms = query.split(/\s+/).filter(Boolean);
  searchMatches = searchIndex.items.filter((entry) => {
    const searchable = entry.search_text.toLocaleLowerCase();
    return terms.every((term) => searchable.includes(term));
  });
  if (!searchMatches.length) {
    searchSummary.textContent = "No matching specials.";
    return;
  }
  appendSearchResults(SEARCH_INITIAL_RESULTS);
}

function scheduleSearchResults(): void {
  window.clearTimeout(searchDebounceTimer);
  if (!searchInput.value.trim()) {
    searchDebounceTimer = 0;
    renderSearchResults();
    return;
  }
  searchSummary.textContent = "Searching…";
  searchDebounceTimer = window.setTimeout(() => {
    searchDebounceTimer = 0;
    renderSearchResults();
  }, SEARCH_DEBOUNCE_MS);
}

async function openSearch(): Promise<void> {
  searchDialog.showModal();
  searchInput.focus();
  searchSummary.textContent = "Loading search…";
  try {
    await loadSearchIndex();
    renderSearchResults();
  } catch (error) {
    searchSummary.textContent = error instanceof Error ? error.message : "Search is unavailable";
  }
}

async function start(): Promise<void> {
  try {
    const restoreCode = captureRestoreCode();
    const restoreRequest = restoreCode ? requestRestoredState(restoreCode) : null;
    const response = await fetch("./data/manifest.json");
    if (!response.ok) throw new Error(`Catalogue manifest returned ${response.status}`);
    manifest = (await response.json()) as Manifest;
    if (!manifest.page_count) throw new Error("Catalogue contains no pages");
    searchOpen.disabled = false;
    statusElement.textContent = `Updated ${new Date(manifest.generated_at).toLocaleDateString()}${personalStateMessage ? ` · ${personalStateMessage}` : ""}`;
    favouriteProductIds = new Set(
      parseFavouriteIds(localStorage.getItem(FAVOURITES_STORAGE_KEY)),
    );
    const storedLocation = localStorage.getItem(LOCATION_STORAGE_KEY);
    const legacyPage = Number(localStorage.getItem("tucker-catalogue-page") || "1");
    const preferredLocation = storedLocation
      ?? `catalogue:${Number.isFinite(legacyPage) ? Math.max(1, Math.min(legacyPage, manifest.page_count)) : 1}`;
    await refreshPageModel(preferredLocation);
    if (restoreRequest) void applyRestoreResult(restoreRequest);
    else void reconcilePersonalState();
  } catch (error) {
    statusElement.textContent = error instanceof Error ? error.message : "Catalogue failed to load";
    pagesElement.innerHTML = '<p class="fatal-error">Catalogue unavailable. Please try again later.</p>';
  }
}

pagesElement.addEventListener("scroll", () => {
  window.clearTimeout(scrollTimer);
  scrollTimer = window.setTimeout(() => {
    if (rebuildingPageModel) return;
    currentPage = Math.round(pagesElement.scrollLeft / Math.max(1, pagesElement.clientWidth)) + 1;
    updateControls();
  }, 80);
}, { passive: true });
previousButton.addEventListener("click", () => goToPage(currentPage - 1));
nextButton.addEventListener("click", () => goToPage(currentPage + 1));
firstButton.addEventListener("click", () => goToPage(1));
pageSelect.addEventListener("change", () => goToPage(Number(pageSelect.value)));
searchOpen.addEventListener("click", () => void openSearch());
searchClose.addEventListener("click", closeSearch);
searchInput.addEventListener("input", scheduleSearchResults);
searchDialog.addEventListener("click", (event) => {
  if (event.target === searchDialog) closeSearch();
});
settingsOpen.addEventListener("click", () => {
  settingsDialog.showModal();
  settingsClose.focus();
});
settingsClose.addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("click", (event) => {
  if (event.target === settingsDialog) settingsDialog.close();
});
(Object.keys(DEFAULT_COLOURS) as ColourKey[]).forEach((key) => {
  colourControls[key].input.addEventListener("input", saveSelectedColours);
});
settingsDefault.addEventListener("click", () => {
  localStorage.removeItem(COLOUR_STORAGE_KEY);
  applyColours({ ...DEFAULT_COLOURS });
  markPersonalSyncPending(700);
});
productDialogClose.addEventListener("click", closeProductDialog);
productDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeProductDialog();
});
productDialog.addEventListener("click", (event) => {
  if (event.target === productDialog) closeProductDialog();
});
productDialog.addEventListener("close", () => {
  window.clearTimeout(dialogCloseTimer);
  productDialog.classList.remove("is-closing");
  const opener = dialogOpener;
  const item = dialogItem;
  const favouriteChanged = item !== null && dialogInitialFavourite !== isFavourite(item);
  let preferredKey = pageDescriptors[currentPage - 1]?.key ?? null;
  if (item && dialogInitialFavourite && !isFavourite(item)) {
    const sourcePage = searchIndex?.items.find((entry) => entry.id === item.id)?.page;
    if (sourcePage) preferredKey = `catalogue:${sourcePage}`;
  }
  dialogOpener = null;
  dialogItem = null;
  if (favouriteChanged) {
    void refreshPageModel(preferredKey)
      .catch((error) => {
        statusElement.textContent = error instanceof Error ? error.message : "Favourites could not be refreshed";
      })
      .finally(() => {
        if (opener?.isConnected) opener.focus();
        else searchOpen.focus();
      });
  } else if (opener?.isConnected) {
    opener.focus();
  }
});

applyColours(loadColours());
void start();
