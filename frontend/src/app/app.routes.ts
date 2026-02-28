import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat-page.component';
import { AgentsPageComponent } from './pages/agents-page.component';
import { SettingsPageComponent } from './pages/settings-page.component';
import { TestsPageComponent } from './pages/tests-page.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'chat' },
	{ path: 'chat', component: ChatPageComponent },
	{ path: 'agents', component: AgentsPageComponent },
	{ path: 'settings', component: SettingsPageComponent },
	{ path: 'tests', component: TestsPageComponent },
];
