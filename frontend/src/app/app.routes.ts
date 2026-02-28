import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat-page.component';

export const routes: Routes = [
	{ path: '', component: ChatPageComponent },
	{ path: '**', redirectTo: '' },
];
