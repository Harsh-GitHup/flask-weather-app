(function () {
    "use strict";

    angular.module("weatherApp", [])
        .config(["$interpolateProvider", function ($interpolateProvider) {
            $interpolateProvider.startSymbol('[[');
            $interpolateProvider.endSymbol(']]');
        }])
        .factory("WeatherApi", ["$http", function ($http) {
            function fetchByCity(q, units) {
                const params = new URLSearchParams({ q, units });
                return $http.get(`/api/weather?${params.toString()}`, { timeout: 10000 })
                    .then(res => res.data);
            }
            return { fetchByCity };
        }])
        .controller("WeatherCtrl", ["WeatherApi", "$scope", function (WeatherApi, $scope) {
            const vm = this;
            vm.query = "Sagar,IN"; // Bengaluru
            vm.units = "metric";
            vm.loading = false;
            vm.error = null;

            // Data
            vm.data = { forecast: { list: [] }, current: null, place: null };
            vm.groupedForecast = [];
            vm.slots = [];

            // ---- Utils ----
            vm.iconUrl = function (icon) {
                return icon ? `https://openweathermap.org/img/wn/${icon}@2x.png` : "";
            };

            vm.speedUnit = function () {
                return vm.units === "imperial" ? "mph" : "m/s";
            };

            vm.placeName = function () {
                const p = vm.data.place || {};
                return [p.name, p.state, p.country].filter(Boolean).join(", ") || "Your location";
            };

            // ---- Forecast Helpers ----
            function buildGroupedForecast(list) {
                if (!list) return [];

                const grouped = {};
                list.forEach(item => {
                    const date = new Date(item.dt * 1000);

                    // LOCAL DATE KEY
                    const dayKey = date.getFullYear() + "-" + (date.getMonth() + 1) + "-" + date.getDate();

                    if (!grouped[dayKey]) {
                        grouped[dayKey] = {
                            label: date.toLocaleDateString(undefined, {
                                weekday: "short",
                                month: "short",
                                day: "numeric"
                            }),
                            items: []
                        };
                    }
                    grouped[dayKey].items.push(item);
                });

                return Object.values(grouped).slice(0, 5); // only 5 days
            }

            // 4 fixed time slots
            function buildTimeSlots() {
                return [
                    { label: "🌅 Morning", hours: [6, 9, 12] },
                    { label: "☀️ Afternoon", hours: [12, 15, 18] },
                    { label: "🌇 Evening", hours: [18, 21] },
                    { label: "🌙 Night", hours: [0, 3, 21, 23] }
                ];
            }

            vm.formatSlotLabel = function (slot) {
                return slot.label;
            };

            vm.findForecastForSlot = function (items, slot) {
                if (!items || !slot.hours) return null;

                // Pick the forecast item closest to slot hours
                let best = null;
                let bestDiff = Infinity;
                items.forEach(it => {
                    const h = new Date(it.dt * 1000).getHours();
                    slot.hours.forEach(sh => {
                        const diff = Math.abs(h - sh);
                        if (diff < bestDiff) {
                            best = it;
                            bestDiff = diff;
                        }
                    });
                });
                return best;
            };

            // ---- Temp Styling ----
            vm.tempStyle = function (temp) {
                if (temp == null) return {};
                let min, max;
                if (vm.units === "imperial") {
                    min = -20; max = 110;
                } else if (vm.units === "metric") {
                    min = -10; max = 45;
                } else {
                    min = 260; max = 320;
                }
                const clamped = Math.max(min, Math.min(temp, max));
                const ratio = (clamped - min) / (max - min);
                const hue = (1 - ratio) * 220;
                return {
                    "color": `hsl(${hue}, 70%, 25%)`,
                    "background-color": `hsl(${hue}, 85%, 90%)`,
                    "border-radius": "0.25rem",
                    "padding": "0.25rem"
                };
            };

            // ---- Labels ----
            vm.unitsLabel = function () {
                switch (vm.units) {
                    case "imperial": return "°F";
                    case "standard": return "K";
                    default: return "°C";
                }
            };

            vm.localTZLabel = function () {
                return Intl.DateTimeFormat().resolvedOptions().timeZone || "local time";
            };

            vm.legendLowLabel = function () {
                return vm.units === "imperial" ? "≤ 32°F" :
                    vm.units === "metric" ? "≤ 0°C" : "≤ 273K";
            };
            vm.legendMidLabel = function () {
                return vm.units === "imperial" ? "60–75°F" :
                    vm.units === "metric" ? "15–24°C" : "288–297K";
            };
            vm.legendHighLabel = function () {
                return vm.units === "imperial" ? "≥ 90°F" :
                    vm.units === "metric" ? "≥ 32°C" : "≥ 305K";
            };

            // ---- API Search ----
            vm.search = function () {
                vm.loading = true;
                vm.error = null;

                WeatherApi.fetchByCity(vm.query, vm.units)
                    .then(function (data) {
                        if (!data || !data.current) {
                            vm.error = "No weather data found.";
                            vm.data = { forecast: { list: [] }, current: null, place: null };
                            vm.groupedForecast = [];
                            vm.slots = [];
                        } else {
                            vm.data = data;
                            vm.groupedForecast = buildGroupedForecast(data.forecast.list);
                            vm.slots = buildTimeSlots();
                        }
                        $scope.$evalAsync();
                    })
                    .catch(function (err) {
                        console.error(err);
                        vm.error = (err && err.data && err.data.error)
                            ? err.data.error
                            : "Failed to load weather.";
                    })
                    .finally(function () {
                        vm.loading = false;
                        $scope.$evalAsync();
                    });
            };

            // initial search
            vm.search();
        }]);

})();
