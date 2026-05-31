import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Chat } from "./components/Chat";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Login } from "./pages/Login";

/** Redirect to /login if the user has no active token. */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Chat />
              </ProtectedRoute>
            }
          />
          {/* Catch-all — send unknown paths to root (which redirects to login if unauthed) */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
