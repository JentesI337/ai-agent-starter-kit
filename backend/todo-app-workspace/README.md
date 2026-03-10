# Todo Application

This is a simple Todo application with an Angular-like frontend and a RESTful API backend.

## Project Structure

```
todo-app-workspace/
├── backend/
│   ├── server.js      # Node.js Express server
│   └── package.json   # Project dependencies
└── frontend/
    └── index.html     # Simple HTML/CSS/JS frontend
```

## Backend API

The backend is a RESTful API built with Node.js and Express that provides the following endpoints:

- `GET /api/todos` - Get all todos
- `GET /api/todos/:id` - Get a specific todo
- `POST /api/todos` - Create a new todo
- `PUT /api/todos/:id` - Update a todo
- `DELETE /api/todos/:id` - Delete a todo

### Running the Backend

1. Navigate to the `backend` directory
2. Install dependencies: `npm install`
3. Start the server: `npm start`
4. The API will be available at `http://localhost:3000`

## Frontend

The frontend is a simple HTML/CSS/JavaScript implementation that communicates with the backend API.

### Running the Frontend

1. Serve the `frontend/index.html` file using any static file server
2. The frontend expects the backend API to be running at `http://localhost:3000`

For example, you can use Python's built-in server:
```bash
cd frontend
python -m http.server 8000
```

Then visit `http://localhost:8000` in your browser.

## Development Notes

Due to environment constraints, we couldn't create a full Angular application. Instead, we provided a simple frontend implementation that demonstrates how to interact with the RESTful API. To upgrade to a full Angular application, you would:

1. Install Angular CLI: `npm install -g @angular/cli`
2. Generate a new Angular app: `ng new todo-angular-frontend`
3. Implement the components and services to communicate with the backend API