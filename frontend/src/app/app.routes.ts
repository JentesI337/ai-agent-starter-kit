import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat-page.component';
import { MemoryPageComponent } from './pages/memory-page.component';

export const routes: Routes = [
	{ path: '', component: ChatPageComponent },
	{ path: 'memory', component: MemoryPageComponent },
	{ path: 'debug', loadComponent: () => import('./pages/debug-page/debug-page.component').then(m => m.DebugPageComponent) },
	{ path: 'debug/dashboard', loadComponent: () => import('./pages/debug-page/debug-dashboard/debug-dashboard.component').then(m => m.DebugDashboardComponent) },
	{ path: '**', redirectTo: '' },
];
