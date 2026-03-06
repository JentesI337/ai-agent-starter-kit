/**
 * SEC (FE-05): Encrypted localStorage wrapper.
 *
 * Uses the Web Crypto API (AES-GCM) to encrypt values before storing them
 * in localStorage.  A per-session encryption key is derived from a random
 * seed stored in sessionStorage — this means data does NOT survive a full
 * browser restart (defense-in-depth: limits the window if XSS ever leaks
 * localStorage contents).
 *
 * For the current POC the only stored value is `preferredRuntime` which is
 * not sensitive, but this service future-proofs the app against accidental
 * storage of tokens or other secrets.
 */
import { Injectable } from '@angular/core';

const SEED_KEY = '__ss_seed';
const ALGO = 'AES-GCM';
const IV_BYTES = 12;

@Injectable({ providedIn: 'root' })
export class SecureStorageService {
  private keyPromise: Promise<CryptoKey> | null = null;

  // ── public API ────────────────────────────────────────────────────────

  async setItem(key: string, value: string): Promise<void> {
    try {
      const cryptoKey = await this.getOrCreateKey();
      const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
      const encoded = new TextEncoder().encode(value);
      const ciphertext = await crypto.subtle.encrypt(
        { name: ALGO, iv },
        cryptoKey,
        encoded,
      );
      // Store as base64: iv + ciphertext
      const combined = new Uint8Array(iv.length + new Uint8Array(ciphertext).length);
      combined.set(iv);
      combined.set(new Uint8Array(ciphertext), iv.length);
      localStorage.setItem(key, this.toBase64(combined));
    } catch {
      // Fallback: store plaintext if crypto is unavailable (e.g. HTTP context)
      localStorage.setItem(key, value);
    }
  }

  async getItem(key: string): Promise<string | null> {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;

    try {
      const cryptoKey = await this.getOrCreateKey();
      const combined = this.fromBase64(raw);
      if (combined.length <= IV_BYTES) {
        // Too short to be encrypted — return raw (migration path)
        return raw;
      }
      const iv = combined.slice(0, IV_BYTES);
      const ciphertext = combined.slice(IV_BYTES);
      const decrypted = await crypto.subtle.decrypt(
        { name: ALGO, iv },
        cryptoKey,
        ciphertext,
      );
      return new TextDecoder().decode(decrypted);
    } catch {
      // Decryption failed — likely a plaintext value from before encryption
      // was enabled.  Return raw as fallback (transparent migration).
      return raw;
    }
  }

  removeItem(key: string): void {
    localStorage.removeItem(key);
  }

  // ── internals ─────────────────────────────────────────────────────────

  private async getOrCreateKey(): Promise<CryptoKey> {
    if (!this.keyPromise) {
      this.keyPromise = this.deriveKey();
    }
    return this.keyPromise;
  }

  private async deriveKey(): Promise<CryptoKey> {
    let seed = sessionStorage.getItem(SEED_KEY);
    if (!seed) {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      seed = this.toBase64(bytes);
      sessionStorage.setItem(SEED_KEY, seed);
    }
    const rawKey = this.fromBase64(seed);
    return crypto.subtle.importKey('raw', rawKey.buffer as ArrayBuffer, ALGO, false, [
      'encrypt',
      'decrypt',
    ]);
  }

  private toBase64(bytes: Uint8Array): string {
    let binary = '';
    for (const b of bytes) {
      binary += String.fromCharCode(b);
    }
    return btoa(binary);
  }

  private fromBase64(b64: string): Uint8Array {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }
}
