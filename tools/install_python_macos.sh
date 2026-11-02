#!/bin/zsh
# No Python is needed to download and open the official macOS installer.
TW_BOOTSTRAP_DIR="${${(%):-%x}:A:h}"
source "$TW_BOOTSTRAP_DIR/python_installers.conf" || exit 1

confirm_python_install() {
    /usr/bin/osascript -e 'display dialog "Tensile Workbench needs Python 3.14. Download and open the official Python installer, then finish Workbench setup? macOS will ask for administrator approval. Existing Python versions and saved Workbench settings are kept." with title "Install Python 3.14" buttons {"Cancel", "Install Python"} default button "Install Python" cancel button "Cancel" with icon note' >/dev/null 2>&1
}

download_python_installer() {
    /usr/bin/curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
        --silent --show-error --retry 2 --connect-timeout 15 --max-time 300 \
        --output "$1" "$TW_PYTHON_MAC_URL"
}

verify_python_installer() {
    print -r -- "$TW_PYTHON_MAC_SHA256  $1" | /usr/bin/shasum -a 256 -c -
}

open_python_installer() {
    # The ordinary Installer UI handles the licence and administrator approval.
    /usr/bin/open -W "$1"
}

finish_python_install() {
    local installed_python='/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14'
    if [[ ! -x "$installed_python" ]]; then
        print -u2 -r -- 'Python installation was cancelled or did not finish. Rerun Workbench setup to try again.'
        return 1
    fi
    "$installed_python" -c 'import sys,struct,sysconfig; sys.exit(not (sys.version_info[:2]==(3,14) and struct.calcsize("P")==8 and not sysconfig.get_config_var("Py_GIL_DISABLED")))' || return 1
    # This is the certificate-completion step supplied by the verified package.
    local certificate_step='/Applications/Python 3.14/Install Certificates.command'
    if [[ -f "$certificate_step" ]]; then
        /bin/sh "$certificate_step" || return 1
    fi
}

install_python_main() {
    confirm_python_install || { print -r -- 'Python installation cancelled.'; return 1; }
    local install_directory
    install_directory="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/tensile-python.XXXXXX")" || return 1
    local installer_file="$install_directory/python.pkg"
    {
        print -r -- "Downloading Python $TW_PYTHON_INSTALL_VERSION from python.org…"
        download_python_installer "$installer_file" || { print -u2 -r -- 'Download failed. Check your connection or ask IT; rerun setup to retry.'; return 1; }
        verify_python_installer "$installer_file" || { print -u2 -r -- 'Installer checksum did not match. The installer was not opened.'; return 1; }
        print -r -- 'Complete the Python installer and close its window. Workbench setup will then continue.'
        open_python_installer "$installer_file" || return 1
        finish_python_install || return 1
    } always {
        /bin/rm -rf -- "$install_directory"
    }
}

if [[ "$ZSH_EVAL_CONTEXT" == toplevel ]]; then
    install_python_main "$@"
fi
