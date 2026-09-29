import React from 'react';
import { createRoot } from 'react-dom/client';
import SetupGate from './Setup';
import './style.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><SetupGate /></React.StrictMode>);
