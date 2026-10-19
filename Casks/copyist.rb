# Homebrew Cask for Copyist (docs/desktop-app.md).
#
# Install (until this is in homebrew-cask):
#   brew tap digital-defiance/copyist https://github.com/Digital-Defiance/copyist
#   brew install --cask copyist
#
# The DMG is published by .github/workflows/release-mac.yml on version tags (v0.0.1, …).
# After each release, update `version` and both `sha256` values from the workflow summary.

cask "copyist" do
  version "0.0.1"

  on_arm do
    sha256 "0000000000000000000000000000000000000000000000000000000000000000"

    url "https://github.com/Digital-Defiance/copyist/releases/download/v#{version}/Copyist_#{version}_aarch64.dmg"
  end
  on_intel do
    sha256 "0000000000000000000000000000000000000000000000000000000000000000"

    url "https://github.com/Digital-Defiance/copyist/releases/download/v#{version}/Copyist_#{version}_x64.dmg"
  end

  name "Copyist"
  desc "The song, the score, the sound — score-first songwriting on your Mac"
  homepage "https://copyist.digitaldefiance.org/"

  depends_on macos: ">= :ventura"

  app "Copyist.app"

  zap trash: [
    "~/Library/Application Support/Copyist",
    "~/Library/Caches/org.digitaldefiance.copyist",
    "~/Library/Preferences/org.digitaldefiance.copyist.plist",
    "~/Library/WebKit/org.digitaldefiance.copyist",
    "~/Music/Copyist",
  ]
end
