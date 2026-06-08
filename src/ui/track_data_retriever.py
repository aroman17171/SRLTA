import winreg
import os

def get_ac_install_path():
    """Finds Assetto Corsa's install path using the Windows registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\WOW6432Node\Valve\Steam")
        steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
        library_folders = [os.path.join(steam_path, "steamapps", "common")]
        # Additional logic to find other Steam libraries if needed.
        for folder in library_folders:
            ac_path = os.path.join(folder, "assettocorsa")
            if os.path.exists(ac_path):
                return ac_path
    except Exception:
        pass
    return None  # Return None if the AC path isn't found automatically.
def find_track_map(track_name):
    """Finds the path to a track's outline.png file."""
    ac_path = get_ac_install_path()
    if not ac_path:
        return None
    
    # Assetto Corsa stores track data in the 'content/tracks' directory.
    track_map_path = os.path.join(ac_path, "content", "tracks", track_name, "ui", "outline.png")
    if os.path.exists(track_map_path):
        return track_map_path
    return None
