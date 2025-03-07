{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # nixpkgs-unfree.url = github:SomeoneSerge/nixpkgs-unfree;
    # nixpkgs-unfree.inputs.nixpkgs.follows = "nixpkgs";
    # nixpkgs = nixgl.inputs.nixpkgs.follows = "nixpkgs";
    nixgl.url = "github:kenranunderscore/nixGL";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs = {self, nixpkgs, nixgl, ... }@inp:
    let
      nixpkgs_configs = {
        default={allowUnfree= true;};
        with_cuda={
          cudaCapabilities = ["8.6"];
          cudaSupport = true;
          allowUnfree = true;
        };
      };
      system = "x86_64-linux";
    in
    {
      # enter this python environment by executing `nix shell .`
      devShells."${system}" = nixpkgs.lib.attrsets.mapAttrs (name: config:
          let pkgs = import nixpkgs { overlays=[nixgl.overlay]; inherit system config;};
              python = pkgs.python311.override {
                packageOverrides = import ./nix/python-overrides.nix;
              };
              cmorl = python.pkgs.callPackage ./nix/cmorl.nix { inherit python; };
          in pkgs.mkShell {
              buildInputs = [
                  pkgs.nixgl.nixGLIntel
                  pkgs.ffmpeg
                  (python.withPackages (p: cmorl.propagatedBuildInputs))
              ];
              shellHook = ''
                export PYTHONPATH=$PYTHONPATH:$(pwd) # to allow cmorl to be imported as editable
                export LD_LIBRARY_PATH=${pkgs.wayland}/lib:$LD_LIBRARY_PATH:/run/opengl-driver/lib
              '';
            }
        ) nixpkgs_configs;
    };
}
