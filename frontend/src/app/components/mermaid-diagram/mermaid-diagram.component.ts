import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnChanges,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import mermaid from 'mermaid';

let _mermaidInitialized = false;
let _idCounter = 0;

function ensureMermaidInit(): void {
  if (_mermaidInitialized) return;
  _mermaidInitialized = true;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#00cc7a',
      primaryBorderColor: '#00cc7a',
      primaryTextColor: '#d4d4d4',
      secondaryColor: '#252526',
      tertiaryColor: '#2d2d30',
      lineColor: '#9b9b9b',
      textColor: '#d4d4d4',
      mainBkg: '#252526',
      nodeBorder: '#00cc7a',
      clusterBkg: '#1e1e1e',
      titleColor: '#d4d4d4',
      edgeLabelBackground: '#1e1e1e',
    },
    flowchart: { curve: 'basis' },
    securityLevel: 'strict',
  });
}

@Component({
  selector: 'app-mermaid-diagram',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="diagram-container">
      <div class="diagram-content" #diagramEl></div>
      <div class="diagram-error" *ngIf="error">
        {{ error }}
        <pre class="diagram-source" *ngIf="showSource">{{ code }}</pre>
      </div>
      <div class="diagram-actions" *ngIf="!error && rendered">
        <button (click)="exportSvg()" title="Download SVG">SVG</button>
        <button (click)="exportPng()" title="Download PNG">PNG</button>
      </div>
    </div>
  `,
  styleUrls: ['./mermaid-diagram.component.scss'],
})
export class MermaidDiagramComponent implements AfterViewInit, OnChanges {
  @Input() code = '';
  @Input() diagramId = '';
  @ViewChild('diagramEl') diagramEl!: ElementRef<HTMLDivElement>;

  error = '';
  rendered = false;
  showSource = false;
  private _uniqueId = '';

  ngAfterViewInit(): void {
    this._uniqueId = this.diagramId || `mermaid-${++_idCounter}`;
    this.renderDiagram();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['code'] && !changes['code'].firstChange) {
      this.renderDiagram();
    }
  }

  private async renderDiagram(): Promise<void> {
    if (!this.code || !this.diagramEl) return;
    ensureMermaidInit();
    this.error = '';
    this.rendered = false;
    this.showSource = false;

    try {
      const { svg } = await mermaid.render(this._uniqueId, this.code);
      this.diagramEl.nativeElement.innerHTML = svg;
      this.rendered = true;
    } catch (err: unknown) {
      this.error = 'Diagram could not be rendered \u2014 the syntax may be invalid.';
      this.showSource = true;
      this.diagramEl.nativeElement.innerHTML = '';
    }
  }

  exportSvg(): void {
    const svg = this.diagramEl?.nativeElement.querySelector('svg');
    if (!svg) return;
    const blob = new Blob([svg.outerHTML], { type: 'image/svg+xml' });
    this.downloadBlob(blob, 'diagram.svg');
  }

  exportPng(): void {
    const svg = this.diagramEl?.nativeElement.querySelector('svg');
    if (!svg) return;

    const svgData = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth * 2;
      canvas.height = img.naturalHeight * 2;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.scale(2, 2);
      ctx.drawImage(img, 0, 0);
      canvas.toBlob((blob) => {
        if (blob) this.downloadBlob(blob, 'diagram.png');
      }, 'image/png');
    };
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
