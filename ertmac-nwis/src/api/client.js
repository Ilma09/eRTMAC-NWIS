// Shared HTTP client for every page that talks to the backend.
// All API calls in this app import `api` from here instead of using axios
// directly, so the backend's address only has to be set in one place.
import axios from "axios";

// The FastAPI backend's address. Change this if the backend ever runs on a
// different host/port (e.g. deploying it somewhere other than localhost).
export const API_BASE_URL = "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
});

export default api;
