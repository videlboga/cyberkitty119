import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { TelegramProvider } from './app/providers/TelegramProvider'
import { AuthBootstrap } from './app/providers/AuthBootstrap'
import { getBasePath } from './lib/basePath'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

const basename = getBasePath()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TelegramProvider>
        <BrowserRouter basename={basename}>
          <AuthBootstrap />
          <App />
        </BrowserRouter>
      </TelegramProvider>
    </QueryClientProvider>
  </StrictMode>
)
