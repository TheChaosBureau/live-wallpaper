# SPDX-License-Identifier: Apache-2.0
# NixOS module: installs live-wallpaper, the cam list and the refresh timer.
flake:
{ config, lib, pkgs, ... }:
let
  cfg = config.programs.live-wallpaper;
  camsJson = pkgs.writeText "live-wallpaper-cams-unchecked.json" (builtins.toJSON cfg.cams);
  # Run the app's own parser over the list at build time, so a bad cam fails
  # the build and not the timer.
  checkedCams = pkgs.runCommand "live-wallpaper-cams.json" { } ''
    LIVE_WALLPAPER_CAMS=${camsJson} HOME=$TMPDIR ${lib.getExe cfg.package} list > /dev/null
    cp ${camsJson} $out
  '';
  ids = map (cam: cam.id or "") cfg.cams;
in
{
  options.programs.live-wallpaper = {
    enable = lib.mkEnableOption "live-wallpaper, a webcam frame as the GNOME wallpaper";

    package = lib.mkOption {
      type = lib.types.package;
      default = flake.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "live-wallpaper.packages.\${system}.default";
      description = "The live-wallpaper package to use.";
    };

    cams = lib.mkOption {
      type = lib.types.listOf (lib.types.attrsOf (lib.types.oneOf [ lib.types.str lib.types.int ]));
      default = [ ];
      example = lib.literalExpression ''
        [
          { id = "my-cam"; name = "My cam"; kind = "latest"; url = "https://example.org/cam.jpg"; }
        ]
      '';
      description = ''
        Cams added to the built-in list, written to /etc/live-wallpaper/cams.json.
        See the README for the fields. You are responsible for the terms of
        any cam you add.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [{
      assertion = lib.allUnique ids;
      message = "programs.live-wallpaper.cams: two cams share an id";
    }];

    environment.systemPackages = [ cfg.package ];

    environment.etc = lib.mkIf (cfg.cams != [ ]) {
      "live-wallpaper/cams.json".source = checkedCams;
    };

    systemd.user.services.live-wallpaper = {
      description = "Refresh the webcam wallpaper";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${lib.getExe cfg.package} refresh";
        NoNewPrivileges = true;
        Nice = 19;
        TimeoutStartSec = 120;
      };
    };

    systemd.user.timers.live-wallpaper = {
      description = "Refresh the webcam wallpaper every 5 minutes";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "*:0/5";
        Persistent = false;
      };
    };
  };
}
