import api from "../api/axios";

export const alertService = {
  // GET /api/v1/alerts/
  getAlerts: async (params = {}) => {
    // Allows passing { status: 'ACTIVE', priority: 'critical' } if needed
    const response = await api.get("/alerts/", { params });
    return response.data;
  },

  // GET /api/v1/alerts/stats
  getAlertStats: async () => {
    const response = await api.get("/alerts/stats");
    return response.data; 
  },

  // POST /api/v1/alerts/{alert_id}/resolve
  resolveAlert: async (alertId) => {
    const response = await api.post(`/alerts/${alertId}/resolve`);
    return response.data;
  },

  // POST /api/v1/alerts/{alert_id}/snooze
  // Added hours param as per Swagger (default 24)
  snoozeAlert: async (alertId, hours = 24) => {
    const response = await api.post(`/alerts/${alertId}/snooze`, null, {
      params: { hours }
    });
    return response.data;
  },

  // NEW: POST /api/v1/alerts/trigger-check
  triggerCheck: async () => {
    const response = await api.post("/alerts/trigger-check");
    return response.data;
  }
};