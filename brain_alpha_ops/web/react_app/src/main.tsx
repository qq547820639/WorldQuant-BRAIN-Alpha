import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import ErrorBoundary from '@/components/ErrorBoundary';
import NotFound from '@/components/NotFound';
import { GlobalDataProvider } from '@/hooks/useGlobalData';
import './index.css';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ErrorBoundary>
      <GlobalDataProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<App />} />
            <Route path="/config" element={<App />} />
            <Route path="/candidates" element={<App />} />
            <Route path="/scoring" element={<App />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </GlobalDataProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
