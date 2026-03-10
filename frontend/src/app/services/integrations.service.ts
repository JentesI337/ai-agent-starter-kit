import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ConnectorSummary {
	connector_id: string;
	connector_type: string;
	display_name: string;
	base_url: string;
	auth_type: string;
	has_credentials: boolean;
	available_methods: any[];
	rate_limit_rps: number;
	rate_limit_burst: number;
	auto_refresh_token: boolean;
}

export interface ConnectorDetail {
	connector_id: string;
	connector_type: string;
	display_name: string;
	base_url: string;
	auth_type: string;
	rate_limit_rps: number;
	rate_limit_burst: number;
	default_headers: Record<string, string>;
	timeout_seconds: number;
	max_response_bytes: number;
	auto_refresh_token: boolean;
	oauth2_client_id: string | null;
	oauth2_scopes: string[];
	has_credentials: boolean;
	available_methods: any[];
}

export interface ConnectorCreateRequest {
	connector_id: string;
	connector_type: string;
	display_name: string;
	base_url: string;
	auth_type: string;
	rate_limit_rps?: number;
	rate_limit_burst?: number;
	timeout_seconds?: number;
	auto_refresh_token?: boolean;
	oauth2_client_id?: string;
	oauth2_scopes?: string[];
	api_key?: string;
	credentials_extra?: Record<string, string>;
}

@Injectable({ providedIn: 'root' })
export class IntegrationsService {
	private base = 'http://localhost:8000';

	constructor(private http: HttpClient) {}

	listConnectors(): Observable<{ connectors: ConnectorSummary[] }> {
		return this.http.post<{ connectors: ConnectorSummary[] }>(
			`${this.base}/api/control/integrations.connectors.list`, {}
		);
	}

	getConnector(id: string): Observable<{ connector: ConnectorDetail }> {
		return this.http.post<{ connector: ConnectorDetail }>(
			`${this.base}/api/control/integrations.connectors.get`,
			{ connector_id: id }
		);
	}

	createConnector(config: ConnectorCreateRequest): Observable<{ connector: ConnectorDetail }> {
		return this.http.post<{ connector: ConnectorDetail }>(
			`${this.base}/api/control/integrations.connectors.create`, config
		);
	}

	updateConnector(id: string, updates: Partial<ConnectorCreateRequest>): Observable<{ connector: ConnectorDetail }> {
		return this.http.post<{ connector: ConnectorDetail }>(
			`${this.base}/api/control/integrations.connectors.update`,
			{ connector_id: id, ...updates }
		);
	}

	deleteConnector(id: string): Observable<{ ok: boolean }> {
		return this.http.post<{ ok: boolean }>(
			`${this.base}/api/control/integrations.connectors.delete`,
			{ connector_id: id }
		);
	}

	testConnector(id: string): Observable<{ ok: boolean; latency_ms: number; error?: string }> {
		return this.http.post<{ ok: boolean; latency_ms: number; error?: string }>(
			`${this.base}/api/control/integrations.connectors.test`,
			{ connector_id: id }
		);
	}

	startOAuth(connectorId: string): Observable<{ authorization_url: string; state: string }> {
		return this.http.post<{ authorization_url: string; state: string }>(
			`${this.base}/api/control/integrations.oauth.start`,
			{ connector_id: connectorId }
		);
	}

	pollOAuthStatus(connectorId: string): Observable<{ complete: boolean }> {
		return this.http.post<{ complete: boolean }>(
			`${this.base}/api/control/integrations.oauth.status`,
			{ connector_id: connectorId }
		);
	}
}
