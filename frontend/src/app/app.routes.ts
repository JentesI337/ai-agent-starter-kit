import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat-page.component';

export const routes: Routes = [
	{ path: '', component: ChatPageComponent },
	{ path: 'live', loadComponent: () => import('./pages/live-page.component').then(m => m.LivePageComponent) },
	{ path: 'debug', loadComponent: () => import('./pages/debug-page/debug-page.component').then(m => m.DebugPageComponent) },
	{ path: 'debug/dashboard', loadComponent: () => import('./pages/debug-page/debug-dashboard/debug-dashboard.component').then(m => m.DebugDashboardComponent) },
	{ path: 'agents', loadComponent: () => import('./pages/agents-page/agents-page.component').then(m => m.AgentsPageComponent) },
	{ path: 'settings', loadComponent: () => import('./pages/settings-page/settings-page.component').then(m => m.SettingsPageComponent) },
	{ path: 'recipes', loadComponent: () => import('./pages/recipes-page/recipes-page.component').then(m => m.RecipesPageComponent) },
	{ path: 'workflows', redirectTo: 'recipes' },
	{ path: 'workflows/pipeline', redirectTo: 'recipes' },
	{ path: 'workflows/result', redirectTo: 'recipes' },
	{ path: 'integrations', loadComponent: () => import('./pages/integrations-page/integrations-page.component').then(m => m.IntegrationsPageComponent) },
	{ path: 'architecture', loadComponent: () => import('./pages/architecture-page/architecture-page.component').then(m => m.ArchitecturePageComponent) },
	{ path: '**', redirectTo: '' },
];
