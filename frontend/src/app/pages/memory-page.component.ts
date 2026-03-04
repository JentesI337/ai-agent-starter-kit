import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentsService, MemoryOverviewResponse } from '../services/agents.service';

@Component({
  selector: 'app-memory-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './memory-page.component.html',
  styleUrl: './memory-page.component.scss',
})
export class MemoryPageComponent implements OnInit {
  memory: MemoryOverviewResponse | null = null;
  loading = false;
  error = '';

  searchTerm = '';
  sessionFilter = '';
  includeContent = true;
  limitSessions = 200;
  limitEntriesPerSession = 500;

  private searchDebounceTimer: number | null = null;
  private pendingReload = false;

  constructor(private readonly agentsService: AgentsService) {}

  ngOnInit(): void {
    this.loadMemory();
  }

  ngOnDestroy(): void {
    if (this.searchDebounceTimer !== null) {
      window.clearTimeout(this.searchDebounceTimer);
      this.searchDebounceTimer = null;
    }
  }

  onSearchTermChanged(): void {
    this.scheduleReload();
  }

  onSessionFilterChanged(): void {
    this.scheduleReload();
  }

  private scheduleReload(): void {
    if (this.searchDebounceTimer !== null) {
      window.clearTimeout(this.searchDebounceTimer);
    }
    this.searchDebounceTimer = window.setTimeout(() => {
      this.searchDebounceTimer = null;
      this.loadMemory();
    }, 350);
  }

  loadMemory(): void {
    if (this.loading) {
      this.pendingReload = true;
      return;
    }
    this.loading = true;
    this.error = '';

    const normalizedSession = this.sessionFilter.trim();
    this.agentsService
      .getMemoryOverview({
        session_id: normalizedSession || undefined,
        search_query: this.searchTerm.trim() || undefined,
        include_content: this.includeContent,
        limit_sessions: this.limitSessions,
        limit_entries_per_session: this.limitEntriesPerSession,
      })
      .subscribe({
        next: (payload) => {
          this.memory = payload;
          this.loading = false;
          if (this.pendingReload) {
            this.pendingReload = false;
            this.loadMemory();
          }
        },
        error: (err) => {
          this.error = err?.error?.detail || err?.message || 'Failed to load memory overview.';
          this.loading = false;
          if (this.pendingReload) {
            this.pendingReload = false;
            this.loadMemory();
          }
        },
      });
  }

  get filteredSessions() {
    if (!this.memory) {
      return [];
    }
    const needle = this.searchTerm.trim().toLowerCase();
    if (!needle) {
      return this.memory.sessions;
    }
    return this.memory.sessions
      .map((session) => {
        const entries = session.entries.filter((entry) => {
          const hay = `${entry.role} ${entry.content || ''}`.toLowerCase();
          return hay.includes(needle);
        });
        const sessionMatch = session.session_id.toLowerCase().includes(needle);
        if (sessionMatch) {
          return session;
        }
        return { ...session, entries, entry_count: entries.length };
      })
      .filter((session) => session.session_id.toLowerCase().includes(needle) || session.entries.length > 0);
  }

  get filteredEpisodic() {
    if (!this.memory) {
      return [];
    }
    const entries = [...this.memory.long_term_memory.episodic].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    const needle = this.searchTerm.trim().toLowerCase();
    if (!needle) {
      return entries;
    }
    return entries.filter((item) => {
      const hay = `${item.session_id} ${item.summary || ''} ${item.tags} ${item.key_actions}`.toLowerCase();
      return hay.includes(needle);
    });
  }

  get filteredSemantic() {
    if (!this.memory) {
      return [];
    }
    const entries = [...this.memory.long_term_memory.semantic].sort((a, b) => {
      const keySort = a.key.localeCompare(b.key);
      if (keySort !== 0) {
        return keySort;
      }
      return b.last_updated.localeCompare(a.last_updated);
    });
    const needle = this.searchTerm.trim().toLowerCase();
    if (!needle) {
      return entries;
    }
    return entries.filter((item) => {
      const hay = `${item.key} ${item.value || ''} ${item.source_sessions}`.toLowerCase();
      return hay.includes(needle);
    });
  }

  get filteredFailures() {
    if (!this.memory) {
      return [];
    }
    const entries = [...this.memory.long_term_memory.failure_journal].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    const needle = this.searchTerm.trim().toLowerCase();
    if (!needle) {
      return entries;
    }
    return entries.filter((item) => {
      const hay = `${item.id} ${item.error_type} ${item.task_description || ''} ${item.root_cause || ''} ${item.solution || ''} ${item.tags}`.toLowerCase();
      return hay.includes(needle);
    });
  }
}
