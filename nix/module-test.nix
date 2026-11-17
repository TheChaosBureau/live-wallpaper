# SPDX-License-Identifier: Apache-2.0
# Evaluates the NixOS module and checks what it declares.
{ nixpkgs, pkgs, module }:
let
  lib = nixpkgs.lib;
  eval = cams: (nixpkgs.lib.nixosSystem {
    inherit (pkgs.stdenv.hostPlatform) system;
    modules = [
      module
      {
        programs.live-wallpaper.enable = true;
        programs.live-wallpaper.cams = cams;
        boot.loader.grub.enable = false;
        fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
        system.stateVersion = "26.05";
      }
    ];
  }).config;

  cam = id: { inherit id; name = "Test cam"; kind = "latest"; url = "https://cam.example/latest.jpg"; };
  good = eval [ (cam "test-cam") ];
  duplicate = eval [ (cam "same") (cam "same") ];
  failedAssertions = config: builtins.filter (a: !a.assertion) config.assertions;

  timer = good.systemd.user.timers.live-wallpaper;
  service = good.systemd.user.services.live-wallpaper;
  camsFile = good.environment.etc."live-wallpaper/cams.json".source;
in
assert lib.assertMsg (timer.timerConfig.OnCalendar == "*:0/5") "timer period";
assert lib.assertMsg (timer.wantedBy == [ "timers.target" ]) "timer is enabled";
assert lib.assertMsg (lib.hasSuffix "/bin/live-wallpaper refresh" service.serviceConfig.ExecStart) "service command";
assert lib.assertMsg (service.serviceConfig.ProtectHome == "read-only") "home is read-only";
assert lib.assertMsg (service.serviceConfig.ProtectSystem == "strict") "system is read-only";
assert lib.assertMsg (service.serviceConfig.NoNewPrivileges) "no new privileges";
assert lib.assertMsg (builtins.elem "-%h/.cache/live-wallpaper" service.serviceConfig.ReadWritePaths) "cache is writable";
assert lib.assertMsg (builtins.elem "-%h/.local/state/live-wallpaper" service.serviceConfig.ReadWritePaths) "state is writable";
assert lib.assertMsg (failedAssertions good == [ ]) "a good config has no failed assertions";
assert lib.assertMsg (builtins.length (failedAssertions duplicate) == 1) "duplicate ids are refused";
assert lib.assertMsg (!(eval [ ]).environment.etc ? "live-wallpaper/cams.json") "no file without cams";
pkgs.runCommand "live-wallpaper-module-test" { nativeBuildInputs = [ pkgs.jq ]; } ''
  # building this also runs the app's parser over the cam list
  test "$(jq -r '.[0].id' ${camsFile})" = test-cam
  touch $out
''
