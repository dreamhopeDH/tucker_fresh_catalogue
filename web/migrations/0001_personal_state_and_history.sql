PRAGMA foreign_keys = ON;

CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    sync_code TEXT NOT NULL UNIQUE,
    history_enabled INTEGER NOT NULL DEFAULT 0 CHECK (history_enabled IN (0, 1)),
    customization_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX one_history_enabled_profile
    ON profiles(history_enabled)
    WHERE history_enabled = 1;

CREATE TABLE profile_favourites (
    profile_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    PRIMARY KEY (profile_id, product_id),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE INDEX profile_favourites_product_id
    ON profile_favourites(product_id);

CREATE TABLE history_checkpoints (
    checkpoint_date TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    favourites_json TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE INDEX history_checkpoints_profile_date
    ON history_checkpoints(profile_id, checkpoint_date);

CREATE TABLE tracked_products (
    product_id TEXT PRIMARY KEY,
    first_checkpoint_date TEXT NOT NULL,
    first_tracked_at TEXT NOT NULL,
    last_known_name TEXT
);

CREATE TABLE price_history (
    product_id TEXT NOT NULL,
    checkpoint_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    is_special INTEGER NOT NULL CHECK (is_special IN (0, 1)),
    regular_price_cents INTEGER NULL,
    special_price_cents INTEGER NULL,
    saving_cents INTEGER NULL,
    discount_percent REAL NULL,
    price_unit TEXT NULL,
    offer_text TEXT NULL,
    PRIMARY KEY (product_id, checkpoint_date),
    FOREIGN KEY (product_id) REFERENCES tracked_products(product_id)
);

CREATE INDEX price_history_checkpoint_date
    ON price_history(checkpoint_date);
