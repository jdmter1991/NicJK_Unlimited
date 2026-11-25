#!/bin/bash
# Utility script to be ran post-install to move and codesign files

# Define paths
TAYST_DIR=~/Library/Application\ Support/NicJK
JEDI_DIR=~/Library/Application\ Support/Steam/steamapps/common/Jedi\ Academy/JediAcademy
TAYST_APP=$TAYST_DIR/nicjk.arm64.app
TAYST_DED=$TAYST_DIR/nicjkded.arm64

# Check NicJK destination directory exists
if [ ! -d "$TAYST_DIR" ]; then
    echo "Error: NicJK directory not found at $TAYST_DIR"
    exit 1
fi

# Check new files are present in Jedi Academy directory
if [ ! -d "$JEDI_DIR/nicjk.arm64.app" ]; then
    echo "Error: Jedi Academy files not found. Make sure the game is installed through Steam."
    exit 1
fi

# Remove existing NicJK files
rm -rf "$TAYST_DIR/nicjk.arm64.app" "$TAYST_DIR/nicjk/" "$TAYST_DIR/nicjkded.arm64"

# Move new files to NicJK folder
mv "$JEDI_DIR"/* "$TAYST_DIR"

# Remove quarantine attribute
xattr -r -d com.apple.quarantine "$TAYST_APP"
xattr -r -d com.apple.quarantine "$TAYST_DED"

# Sign the application bundle and dedicated server binary
codesign --force --deep --sign - "$TAYST_APP"
codesign --force --sign - "$TAYST_DED"

echo "NicJK setup completed successfully!"