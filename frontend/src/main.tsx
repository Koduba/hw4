import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './lib/AuthContext.tsx'
import { ShowcaseProvider } from './lib/ShowcaseContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ShowcaseProvider>
          <App />
        </ShowcaseProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
