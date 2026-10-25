import { Navigate, Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ErrorBoundary'
import { AppLayout } from '@/components/layout/AppLayout'
import { ProtectedRoute } from '@/components/layout/ProtectedRoute'
import { useAuth } from '@/contexts/AuthContext'
import { ApplicationCreatePage } from '@/pages/ApplicationCreatePage'
import { ApplicationDetailPage } from '@/pages/ApplicationDetailPage'
import { ApplicationsListPage } from '@/pages/ApplicationsListPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

function RootRedirect() {
  const { user, token } = useAuth()

  if (!token || !user) {
    return <Navigate to="/login" replace />
  }

  return <Navigate to="/applications" replace />
}

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/applications" element={<ApplicationsListPage />} />
            <Route
              path="/applications/new"
              element={<ApplicationCreatePage />}
            />
            <Route
              path="/applications/:id"
              element={<ApplicationDetailPage />}
            />
          </Route>
        </Route>

        <Route path="/" element={<RootRedirect />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default App
