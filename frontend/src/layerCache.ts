import { jsonFetch } from "./api";

// Hard 1-day expiration for cached layer data. After this window a cached
// entry is considered stale and is re-fetched from the network.
export const LAYER_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

// The large, mostly-static GIS layers (roads and especially the ~2MB hydrants
// GeoJSON) are cached in IndexedDB so a hard refresh can reuse recently fetched
// data instead of re-downloading. localStorage is intentionally NOT used: these
// payloads exceed its size limits. This module is dependency-free (vanilla
// IndexedDB) and degrades gracefully — any IndexedDB failure falls back to a
// normal fetch so the app never breaks.

const DB_NAME = "rcgis-layer-cache";
const STORE_NAME = "layers";
const DB_VERSION = 1;

type CacheEntry<T> = { data: T; fetchedAt: number };

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
  });
}

async function readEntry<T>(key: string): Promise<CacheEntry<T> | null> {
  const db = await openDb();
  try {
    return await new Promise<CacheEntry<T> | null>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).get(key);
      request.onsuccess = () => resolve((request.result as CacheEntry<T> | undefined) ?? null);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

async function writeEntry<T>(key: string, data: T): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const entry: CacheEntry<T> = { data, fetchedAt: Date.now() };
      tx.objectStore(STORE_NAME).put(entry, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

// Result of a cached layer fetch, including whether it was served from the
// IndexedDB cache and when that cached copy was stored (so the UI can report it).
export type CachedLayerResult<T> = { data: T; fromCache: boolean; fetchedAt: number | null };

// Fetch a layer with an IndexedDB-backed cache keyed by `url`, returning cache
// metadata alongside the data.
// - If a cached entry exists and is younger than LAYER_CACHE_TTL_MS, return it
//   immediately (fromCache: true) and skip the network fetch.
// - Otherwise (missing or stale) fetch fresh, update the cache, and return
//   fromCache: false.
// - Pass { force: true } to bypass the cache read and re-fetch (used right after
//   a layer rebuild, so freshly built data is not masked by a recent cache entry).
// - Any IndexedDB error is swallowed and we fall back to a plain fetch.
export async function fetchCachedLayerMeta<T>(
  url: string,
  init?: RequestInit,
  options?: { force?: boolean },
): Promise<CachedLayerResult<T>> {
  if (!options?.force) {
    try {
      const entry = await readEntry<T>(url);
      if (entry && Date.now() - entry.fetchedAt < LAYER_CACHE_TTL_MS) {
        return { data: entry.data, fromCache: true, fetchedAt: entry.fetchedAt };
      }
    } catch {
      // Cache read failed (e.g. IndexedDB unavailable); fall through to network.
    }
  }

  const data = await jsonFetch<T>(url, init);

  try {
    await writeEntry(url, data);
  } catch {
    // Cache write failed; the fetched data is still returned normally.
  }

  return { data, fromCache: false, fetchedAt: Date.now() };
}

// Convenience wrapper returning only the data (when cache status is not needed).
export async function fetchCachedLayer<T>(
  url: string,
  init?: RequestInit,
  options?: { force?: boolean },
): Promise<T> {
  return (await fetchCachedLayerMeta<T>(url, init, options)).data;
}
