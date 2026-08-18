import "./styles.css";

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
  page_count: number;
  pages: string[];
  discount_groups: DiscountGroupSummary[];
  ordering: {
    mode: "deterministic_random";
    seed: number;
  };
};

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
const placeholderUrl = "./placeholder.svg";
const loaded = new Set<number>();
const loading = new Set<number>();
let manifest: Manifest;
let currentPage = 1;
let scrollTimer = 0;
let dialogCloseTimer = 0;
let dialogOpener: HTMLElement | null = null;

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
}

function openProductDialog(item: CatalogueItem, opener: HTMLElement): void {
  window.clearTimeout(dialogCloseTimer);
  productDialog.classList.remove("is-closing");
  populateProductDialog(item);
  dialogOpener = opener;
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

async function loadPage(index: number): Promise<void> {
  if (index < 1 || index > manifest.page_count || loaded.has(index) || loading.has(index)) return;
  loading.add(index);
  const shell = document.querySelector<HTMLElement>(`[data-page="${index}"]`)!;
  try {
    const response = await fetch(manifest.pages[index - 1]);
    if (!response.ok) throw new Error(`page ${index} returned ${response.status}`);
    const data = (await response.json()) as PageData;
    const grid = document.createElement("div");
    grid.className = "product-grid";
    data.items.forEach((item) => grid.append(renderCard(item)));
    shell.replaceChildren(grid);
    loaded.add(index);
  } catch (error) {
    shell.textContent = "This page could not be loaded.";
    statusElement.textContent = error instanceof Error ? error.message : "Page load failed";
  } finally {
    loading.delete(index);
  }
}

function unloadDistantPages(): void {
  loaded.forEach((page) => {
    if (Math.abs(page - currentPage) > 1) {
      const shell = document.querySelector<HTMLElement>(`[data-page="${page}"]`);
      shell?.replaceChildren();
      loaded.delete(page);
    }
  });
}

function groupForPage(page: number): DiscountGroupSummary | undefined {
  return manifest.discount_groups.find((group) =>
    group.start_page !== null
    && page >= group.start_page
    && page < group.start_page + group.page_count
  );
}

function updateControls(): void {
  pageSelect.value = String(currentPage);
  pageLabel.textContent = `Page ${currentPage} of ${manifest.page_count}`;
  discountGroupLabel.textContent = groupForPage(currentPage)?.label ?? "Specials";
  previousButton.disabled = currentPage === 1;
  firstButton.disabled = currentPage === 1;
  nextButton.disabled = currentPage === manifest.page_count;
  localStorage.setItem("tucker-catalogue-page", String(currentPage));
  void loadPage(currentPage - 1);
  void loadPage(currentPage);
  void loadPage(currentPage + 1);
  unloadDistantPages();
}

function goToPage(page: number, behavior: ScrollBehavior = "smooth"): void {
  const target = Math.max(1, Math.min(manifest.page_count, page));
  document.querySelector<HTMLElement>(`[data-page="${target}"]`)?.scrollIntoView({ behavior, inline: "start" });
}

async function start(): Promise<void> {
  try {
    const response = await fetch("./data/manifest.json");
    if (!response.ok) throw new Error(`Catalogue manifest returned ${response.status}`);
    manifest = (await response.json()) as Manifest;
    if (!manifest.page_count) throw new Error("Catalogue contains no pages");
    statusElement.textContent = `Updated ${new Date(manifest.generated_at).toLocaleDateString()}`;
    for (let page = 1; page <= manifest.page_count; page += 1) {
      const shell = document.createElement("section");
      shell.className = "catalogue-page";
      shell.dataset.page = String(page);
      shell.setAttribute("aria-label", `Catalogue page ${page}`);
      pagesElement.append(shell);
      pageSelect.add(new Option(String(page), String(page)));
    }

    const stored = Number(localStorage.getItem("tucker-catalogue-page") || "1");
    currentPage = Number.isFinite(stored) ? Math.max(1, Math.min(stored, manifest.page_count)) : 1;
    await Promise.all([loadPage(currentPage - 1), loadPage(currentPage), loadPage(currentPage + 1)]);
    goToPage(currentPage, "auto");
    updateControls();

    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) void loadPage(Number((entry.target as HTMLElement).dataset.page));
      }),
      { root: pagesElement, rootMargin: "0px 100%", threshold: 0.01 },
    );
    document.querySelectorAll<HTMLElement>(".catalogue-page").forEach((page) => observer.observe(page));
  } catch (error) {
    statusElement.textContent = error instanceof Error ? error.message : "Catalogue failed to load";
    pagesElement.innerHTML = '<p class="fatal-error">Catalogue unavailable. Please try again later.</p>';
  }
}

pagesElement.addEventListener("scroll", () => {
  window.clearTimeout(scrollTimer);
  scrollTimer = window.setTimeout(() => {
    currentPage = Math.round(pagesElement.scrollLeft / Math.max(1, pagesElement.clientWidth)) + 1;
    updateControls();
  }, 80);
}, { passive: true });
previousButton.addEventListener("click", () => goToPage(currentPage - 1));
nextButton.addEventListener("click", () => goToPage(currentPage + 1));
firstButton.addEventListener("click", () => goToPage(1));
pageSelect.addEventListener("change", () => goToPage(Number(pageSelect.value)));
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
  if (dialogOpener?.isConnected) dialogOpener.focus();
  dialogOpener = null;
});

void start();
