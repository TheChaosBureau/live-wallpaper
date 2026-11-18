# SPDX-License-Identifier: Apache-2.0
{
  description = "Show a manually chosen webcam's latest frame as the GNOME wallpaper";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      mkPackage = pkgs: pkgs.python3Packages.buildPythonApplication {
        pname = "live-wallpaper";
        version = "0.2.0";
        pyproject = true;
        src = self;
        build-system = [ pkgs.python3Packages.setuptools ];
        dependencies = [ pkgs.python3Packages.pillow pkgs.python3Packages.pygobject3 ];
        # the settings window is GTK 4
        nativeBuildInputs = [ pkgs.wrapGAppsHook4 pkgs.gobject-introspection ];
        buildInputs = [ pkgs.gtk4 ];
        # One wrapper, not two: the GTK hook's settings (typelibs, the schema
        # that holds the wallpaper keys, the dconf module that makes gsettings
        # write to disk) go into the Python wrapper. The list is built here and
        # not as a Nix attribute, or the Python wrapper keeps only the attribute.
        dontWrapGApps = true;
        preFixup = ''
          makeWrapperArgs+=("''${gappsWrapperArgs[@]}" --prefix PATH : "${pkgs.lib.makeBinPath [ pkgs.glib ]}")
        '';
        nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook pkgs.desktop-file-utils pkgs.xvfb-run ];
        # the window tests drive the real window, on a virtual display
        preCheck = ''
          export HOME=$TMPDIR GSK_RENDERER=cairo GDK_BACKEND=x11 GSETTINGS_BACKEND=memory LIVE_WALLPAPER_WINDOW_TESTS=1
        '';
        checkPhase = ''
          runHook preCheck
          xvfb-run -a -s "-screen 0 1280x800x24" python -m pytest -rs
          runHook postCheck
        '';
        postInstall = ''
          install -Dm644 -t $out/share/applications share/applications/*.desktop
        '';
        postCheck = ''
          for entry in share/applications/*.desktop; do desktop-file-validate "$entry"; echo "valid: $entry"; done
        '';
        meta = {
          description = "Show a manually chosen webcam's latest frame as the GNOME wallpaper";
          license = pkgs.lib.licenses.asl20;
          mainProgram = "live-wallpaper";
          platforms = pkgs.lib.platforms.linux;
        };
      };
    in
    {
      packages = forAll (pkgs: { default = mkPackage pkgs; });
      nixosModules.default = import ./nix/module.nix self;
      checks = forAll (pkgs: {
        package = mkPackage pkgs;
        module = import ./nix/module-test.nix {
          inherit nixpkgs pkgs;
          module = self.nixosModules.default;
        };
      });
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (p: [ p.pytest p.pillow p.pygobject3 ]))
            pkgs.gtk4 pkgs.gobject-introspection pkgs.xvfb-run
          ];
        };
      });
    };
}
