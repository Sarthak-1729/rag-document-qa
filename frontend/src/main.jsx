import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { api } from './api/client.js';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
);
