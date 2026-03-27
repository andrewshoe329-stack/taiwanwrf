import { createBrowserRouter } from 'react-router-dom'
import { App } from './App'
import { NowPage } from './pages/NowPage'
import { SpotsPage } from './pages/SpotsPage'
import { SpotDetailPage } from './pages/SpotDetailPage'
import { ModelsPage } from './pages/ModelsPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <NowPage /> },
      { path: 'spots', element: <SpotsPage /> },
      { path: 'spots/:id', element: <SpotDetailPage /> },
      { path: 'models', element: <ModelsPage /> },
    ],
  },
])
