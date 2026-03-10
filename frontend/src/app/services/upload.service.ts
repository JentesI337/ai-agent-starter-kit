import { Injectable } from '@angular/core';

export interface UploadResult {
  path: string;
  mime_type: string;
  size_bytes: number;
}

@Injectable({ providedIn: 'root' })
export class UploadService {
  private readonly apiUrl = '/api/uploads';

  async uploadFile(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(this.apiUrl, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Upload failed: ${response.status}`);
    }

    return response.json();
  }
}
