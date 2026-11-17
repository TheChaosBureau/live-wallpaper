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
        version = "0.1.0";
        pyproject = true;
        src = self;
        build-system = [ pkgs.python3Packages.setuptools ];
        nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
        makeWrapperArgs = [
          "--prefix" "PATH" ":" (pkgs.lib.makeBinPath [ pkgs.glib pkgs.zenity ])
          # gsettings needs the schema that holds the wallpaper keys
          "--prefix" "XDG_DATA_DIRS" ":"
          "${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}"
        ];
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
      checks = forAll (pkgs: { package = mkPackage pkgs; });
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (p: [ p.pytest ])) ];
        };
      });
    };
}
