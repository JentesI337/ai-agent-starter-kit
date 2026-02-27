import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat-page.component';
import { AgentsPageComponent } from './pages/agents-page.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'chat' },
	{ path: 'chat', component: ChatPageComponent },
	{ path: 'agents', component: AgentsPageComponent },
];
