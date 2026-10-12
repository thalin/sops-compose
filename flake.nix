{
  description = "Author sops creation rules as split YAML with named keys and composable groups";

  inputs.nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "sops-compose";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = [ pkgs.python3Packages.ruamel-yaml ];

          # The shadowing check and the tests shell out to git.
          makeWrapperArgs = [ "--prefix" "PATH" ":" (pkgs.lib.makeBinPath [ pkgs.git ]) ];
          nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook pkgs.python3Packages.pyyaml pkgs.git ];

          meta = {
            description = "Author sops creation rules as split YAML with named keys and composable groups";
            homepage = "https://github.com/thalin/sops-compose";
            license = pkgs.lib.licenses.mit;
            mainProgram = "sops-compose";
          };
        };
      });

      checks = forAllSystems (pkgs: {
        # The package build runs the pytest suite.
        pytest = self.packages.${pkgs.system}.default;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ps.ruamel-yaml ps.pytest ps.pyyaml ]))
            pkgs.git
          ];
        };
      });
    };
}
