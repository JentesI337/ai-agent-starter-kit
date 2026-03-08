import { Routes } from '@angular/router';
import { TodoListComponent } from './todo-list.component';
import { TodoAddComponent } from './todo-add.component';

export const routes: Routes = [
  { path: '', component: TodoListComponent },
  { path: 'add', component: TodoAddComponent }
];