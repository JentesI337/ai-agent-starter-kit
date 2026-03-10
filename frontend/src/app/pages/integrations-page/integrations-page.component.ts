import { Component, ChangeDetectionStrategy, ChangeDetectorRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IntegrationsService, ConnectorSummary, ConnectorDetail, ConnectorCreateRequest } from '../../services/integrations.service';

interface ConnectorTypeCard {
	type: string;
	label: string;
	icon: string;
	defaultBaseUrl: string;
	authTypes: string[];
}

const CONNECTOR_TYPES: ConnectorTypeCard[] = [
	{ type: 'github', label: 'GitHub', icon: '⬡', defaultBaseUrl: 'https://api.github.com', authTypes: ['bearer', 'oauth2_pkce'] },
	{ type: 'jira', label: 'Jira', icon: '▦', defaultBaseUrl: '', authTypes: ['api_key', 'bearer'] },
	{ type: 'slack_webhook', label: 'Slack', icon: '◈', defaultBaseUrl: '', authTypes: ['none'] },
	{ type: 'google', label: 'Google', icon: '◉', defaultBaseUrl: 'https://www.googleapis.com', authTypes: ['oauth2_pkce'] },
	{ type: 'x', label: 'X (Twitter)', icon: '✕', defaultBaseUrl: 'https://api.x.com/2', authTypes: ['bearer', 'oauth2_pkce'] },
	{ type: 'generic_rest', label: 'Custom REST', icon: '⟐', defaultBaseUrl: '', authTypes: ['none', 'api_key', 'bearer'] },
];

@Component({
	selector: 'app-integrations-page',
	standalone: true,
	imports: [CommonModule, FormsModule],
	templateUrl: './integrations-page.component.html',
	styleUrls: ['./integrations-page.component.scss'],
	changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IntegrationsPageComponent implements OnInit, OnDestroy {
	connectorTypes = CONNECTOR_TYPES;
	connectors: ConnectorSummary[] = [];
	selectedConnector: ConnectorDetail | null = null;
	loading = false;
	showCreateModal = false;
	testResult: { ok: boolean; latency_ms: number; error?: string } | null = null;
	testLoading = false;
	oauthPolling = false;

	// Create form
	newConnector: ConnectorCreateRequest = {
		connector_id: '',
		connector_type: 'github',
		display_name: '',
		base_url: 'https://api.github.com',
		auth_type: 'bearer',
		api_key: '',
	};

	private oauthPollTimer: any = null;

	constructor(
		private integrations: IntegrationsService,
		private cdr: ChangeDetectorRef,
	) {}

	ngOnInit() {
		this.loadConnectors();
	}

	ngOnDestroy() {
		if (this.oauthPollTimer) {
			clearInterval(this.oauthPollTimer);
		}
	}

	loadConnectors() {
		this.loading = true;
		this.cdr.markForCheck();
		this.integrations.listConnectors().subscribe({
			next: (res) => {
				this.connectors = res.connectors || [];
				this.loading = false;
				this.cdr.markForCheck();
			},
			error: () => {
				this.loading = false;
				this.cdr.markForCheck();
			},
		});
	}

	selectConnector(c: ConnectorSummary) {
		this.testResult = null;
		this.integrations.getConnector(c.connector_id).subscribe({
			next: (res) => {
				this.selectedConnector = res.connector;
				this.cdr.markForCheck();
			},
		});
	}

	closeDetail() {
		this.selectedConnector = null;
		this.testResult = null;
		this.cdr.markForCheck();
	}

	openCreateModal(typeCard?: ConnectorTypeCard) {
		this.showCreateModal = true;
		if (typeCard) {
			this.newConnector.connector_type = typeCard.type;
			this.newConnector.base_url = typeCard.defaultBaseUrl;
			this.newConnector.auth_type = typeCard.authTypes[0];
		}
		this.cdr.markForCheck();
	}

	closeCreateModal() {
		this.showCreateModal = false;
		this.newConnector = {
			connector_id: '',
			connector_type: 'github',
			display_name: '',
			base_url: 'https://api.github.com',
			auth_type: 'bearer',
			api_key: '',
		};
		this.cdr.markForCheck();
	}

	onTypeChange() {
		const type = this.connectorTypes.find(t => t.type === this.newConnector.connector_type);
		if (type) {
			this.newConnector.base_url = type.defaultBaseUrl;
			this.newConnector.auth_type = type.authTypes[0];
		}
		this.cdr.markForCheck();
	}

	getAuthTypes(): string[] {
		const type = this.connectorTypes.find(t => t.type === this.newConnector.connector_type);
		return type ? type.authTypes : ['none'];
	}

	createConnector() {
		if (!this.newConnector.connector_id || !this.newConnector.display_name) return;
		this.integrations.createConnector(this.newConnector).subscribe({
			next: () => {
				this.closeCreateModal();
				this.loadConnectors();
			},
		});
	}

	deleteConnector(id: string) {
		this.integrations.deleteConnector(id).subscribe({
			next: () => {
				this.selectedConnector = null;
				this.loadConnectors();
			},
		});
	}

	testConnection(id: string) {
		this.testLoading = true;
		this.testResult = null;
		this.cdr.markForCheck();
		this.integrations.testConnector(id).subscribe({
			next: (res) => {
				this.testResult = res;
				this.testLoading = false;
				this.cdr.markForCheck();
			},
			error: () => {
				this.testResult = { ok: false, latency_ms: 0, error: 'Request failed' };
				this.testLoading = false;
				this.cdr.markForCheck();
			},
		});
	}

	startOAuth(id: string) {
		this.integrations.startOAuth(id).subscribe({
			next: (res) => {
				if (res.authorization_url) {
					window.open(res.authorization_url, '_blank');
					this.startOAuthPolling(id);
				}
			},
		});
	}

	private startOAuthPolling(connectorId: string) {
		this.oauthPolling = true;
		this.cdr.markForCheck();
		this.oauthPollTimer = setInterval(() => {
			this.integrations.pollOAuthStatus(connectorId).subscribe({
				next: (res) => {
					if (res.complete) {
						this.oauthPolling = false;
						clearInterval(this.oauthPollTimer);
						this.oauthPollTimer = null;
						this.loadConnectors();
						if (this.selectedConnector?.connector_id === connectorId) {
							this.selectConnector({ connector_id: connectorId } as ConnectorSummary);
						}
						this.cdr.markForCheck();
					}
				},
			});
		}, 2000);
	}

	getTypeIcon(type: string): string {
		return this.connectorTypes.find(t => t.type === type)?.icon || '⟐';
	}

	getTypeLabel(type: string): string {
		return this.connectorTypes.find(t => t.type === type)?.label || type;
	}
}
