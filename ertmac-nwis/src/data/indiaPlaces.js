/*
 * Static, offline place-name labels for the basemap - major Indian metros
 * and state/UT capitals with well-known coordinates. No geocoding service
 * is called for these; they're fixed reference points so the map reads
 * like a real map (place names appearing as you zoom in) while staying
 * fully offline.
 *
 * minZoom controls when a label starts appearing - national metros show
 * first, smaller capitals reveal as the user zooms in further.
 */

export const INDIA_PLACES = [
  // Tier 1 - major metros, visible from country-level zoom
  { name: "Delhi", lat: 28.6139, lng: 77.209, minZoom: 5 },
  { name: "Mumbai", lat: 19.076, lng: 72.8777, minZoom: 5 },
  { name: "Kolkata", lat: 22.5726, lng: 88.3639, minZoom: 5 },
  { name: "Chennai", lat: 13.0827, lng: 80.2707, minZoom: 5 },

  // Tier 2 - other major metros
  { name: "Bengaluru", lat: 12.9716, lng: 77.5946, minZoom: 6 },
  { name: "Hyderabad", lat: 17.385, lng: 78.4867, minZoom: 6 },
  { name: "Ahmedabad", lat: 23.0225, lng: 72.5714, minZoom: 6 },
  { name: "Pune", lat: 18.5204, lng: 73.8567, minZoom: 6 },
  { name: "Jaipur", lat: 26.9124, lng: 75.7873, minZoom: 6 },
  { name: "Lucknow", lat: 26.8467, lng: 80.9462, minZoom: 6 },
  { name: "Guwahati", lat: 26.1445, lng: 91.7362, minZoom: 6 },

  // Tier 3 - remaining state / UT capitals
  { name: "Dehradun", lat: 30.3165, lng: 78.0322, minZoom: 7 },
  { name: "Chandigarh", lat: 30.7333, lng: 76.7794, minZoom: 7 },
  { name: "Bhopal", lat: 23.2599, lng: 77.4126, minZoom: 7 },
  { name: "Patna", lat: 25.5941, lng: 85.1376, minZoom: 7 },
  { name: "Raipur", lat: 21.2514, lng: 81.6296, minZoom: 7 },
  { name: "Ranchi", lat: 23.3441, lng: 85.3096, minZoom: 7 },
  { name: "Bhubaneswar", lat: 20.2961, lng: 85.8245, minZoom: 7 },
  { name: "Thiruvananthapuram", lat: 8.5241, lng: 76.9366, minZoom: 7 },
  { name: "Panaji", lat: 15.4909, lng: 73.8278, minZoom: 7 },
  { name: "Shimla", lat: 31.1048, lng: 77.1734, minZoom: 7 },
  { name: "Srinagar", lat: 34.0837, lng: 74.7973, minZoom: 7 },
  { name: "Gandhinagar", lat: 23.2156, lng: 72.6369, minZoom: 7 },
  { name: "Amaravati", lat: 16.5062, lng: 80.648, minZoom: 7 },

  // Tier 4 - Northeast capitals
  { name: "Imphal", lat: 24.817, lng: 93.9368, minZoom: 8 },
  { name: "Agartala", lat: 23.8315, lng: 91.2868, minZoom: 8 },
  { name: "Shillong", lat: 25.5788, lng: 91.8933, minZoom: 8 },
  { name: "Itanagar", lat: 27.0844, lng: 93.6053, minZoom: 8 },
  { name: "Kohima", lat: 25.6751, lng: 94.1086, minZoom: 8 },
  { name: "Aizawl", lat: 23.7271, lng: 92.7176, minZoom: 8 },
  { name: "Gangtok", lat: 27.3389, lng: 88.6065, minZoom: 8 },
];
