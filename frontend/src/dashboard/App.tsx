import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getToken } from "./api/client";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

function RequireAuth({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
