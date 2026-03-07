import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'syntaxHighlight', standalone: true })
export class SyntaxHighlightPipe implements PipeTransform {
  private rules: [RegExp, string][] = [
    // Markdown Headers → Accent Green
    [/^(#{1,6}\s.+)$/gm, '<span style="color:rgb(0,204,122);font-weight:600">$1</span>'],
    // JSON Keys → Blue
    [/&quot;([^&]+)&quot;\s*:/g, '<span style="color:rgb(55,148,255)">&quot;$1&quot;</span>:'],
    // Strings → Yellow
    [/&quot;([^&]*)&quot;(?!\s*:)/g, '<span style="color:rgb(229,178,0)">&quot;$1&quot;</span>'],
    // Numbers → Cyan
    [/\b(\d+\.?\d*)\b/g, '<span style="color:rgb(86,216,216)">$1</span>'],
    // Booleans → Accent
    [/\b(true|false|null|None)\b/g, '<span style="color:rgb(0,204,122)">$1</span>'],
    // Keywords → Bold
    [/\b(CLASSIFY|Step|TOOL|WHAT|WHY|DEPENDS_ON|FALLBACK)\b/g,
      '<span style="color:rgb(212,212,212);font-weight:600">$1</span>'],
    // Error keywords → Red
    [/\b(error|Error|ERROR|fail|FAIL|exception|Exception)\b/g,
      '<span style="color:#ff5555">$1</span>'],
  ];

  transform(value: string): string {
    if (!value) return '';
    // HTML-Entities escapen gegen Injection
    let escaped = value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    // Rules anwenden
    for (const [regex, replacement] of this.rules) {
      escaped = escaped.replace(regex, replacement);
    }
    return escaped;
  }
}
