// Discord Presence has no dashboard page; its settings live in JettsTUI Desktop.
// Register an empty component so the dashboard does not wait on this plugin.
(function () {
  var registry = window.__JETTSTUI_PLUGINS__;
  if (registry && typeof registry.register === "function") {
    registry.register("discord-presence", function DiscordPresenceHidden() {
      return null;
    });
  }
})();
