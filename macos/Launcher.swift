// Copyright (c) 2026 Brogan Csinger, University of Queensland. MIT License.
import AppKit
import Foundation
import Darwin

// Isolate only the server we launch. Never signal a user's Terminal session.
if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--server-child" {
    if setsid() == -1 && getpgrp() != getpid() {
        perror("Cannot isolate Workbench server")
        exit(1)
    }
    var arguments: [UnsafeMutablePointer<CChar>?] = [
        strdup("/bin/zsh"), strdup(CommandLine.arguments[2]), nil
    ]
    arguments.withUnsafeMutableBufferPointer { _ = execv("/bin/zsh", $0.baseAddress!) }
    perror("Cannot start Workbench launcher")
    exit(1)
}

// Read the existing log incrementally; no Terminal or extra tail process needed.
final class LiveLogWindowController: NSWindowController {
    private let logURL: URL
    private let textView = NSTextView()
    private let scrollView = NSScrollView()
    private let follow = NSButton(checkboxWithTitle: "Auto-scroll", target: nil, action: nil)
    private let status = NSTextField(labelWithString: "Waiting for log output…")
    private var fileIdentity: String?
    private var offset: UInt64 = 0
    private var pendingUTF8 = Data()
    private var discardPartialLine = false
    private var showingTail = false
    private let readLimit = 512 * 1024
    private let displayLimit = 400_000

    init(logURL: URL) {
        self.logURL = logURL
        let logWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 540),
                                 styleMask: [.titled, .closable, .miniaturizable, .resizable],
                                 backing: .buffered, defer: false)
        super.init(window: logWindow)
        logWindow.title = "Tensile Workbench — Live log"
        logWindow.isReleasedWhenClosed = false
        logWindow.minSize = NSSize(width: 540, height: 260)
        logWindow.center()
        logWindow.setFrameAutosaveName("TensileWorkbenchLiveLog")

        follow.state = .on
        follow.target = self
        follow.action = #selector(followChanged)
        let latest = NSButton(title: "Jump to latest", target: self, action: #selector(jumpToLatest))
        let copy = NSButton(title: "Copy log", target: self, action: #selector(copyLog))
        copy.toolTip = "Copy the log text currently shown in this window."
        follow.toolTip = "Untick to read earlier messages without being scrolled to the bottom."
        latest.bezelStyle = .rounded
        copy.bezelStyle = .rounded
        status.font = .systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.lineBreakMode = .byTruncatingTail
        status.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let controls = NSStackView(views: [follow, latest, spacer, copy])
        controls.orientation = .horizontal
        controls.spacing = 10

        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = false
        scrollView.borderType = .bezelBorder
        textView.isEditable = false
        textView.isSelectable = true
        textView.isRichText = false
        textView.allowsUndo = false
        textView.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        textView.textColor = .textColor
        textView.backgroundColor = .textBackgroundColor
        textView.textContainerInset = NSSize(width: 10, height: 10)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.minSize = .zero
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: 860, height: CGFloat.greatestFiniteMagnitude)
        textView.frame = NSRect(x: 0, y: 0, width: 860, height: 450)
        scrollView.documentView = textView
        let content = logWindow.contentView!
        for view in [controls, scrollView, status] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            controls.topAnchor.constraint(equalTo: content.topAnchor, constant: 12),
            controls.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            controls.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            scrollView.topAnchor.constraint(equalTo: controls.bottomAnchor, constant: 10),
            scrollView.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 12),
            scrollView.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -12),
            scrollView.bottomAnchor.constraint(equalTo: status.topAnchor, constant: -8),
            status.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            status.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            status.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -10)
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func open() {
        showWindow(nil)
        refresh()
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func invalidateFile() { fileIdentity = nil }

    func refresh() {
        // Hidden windows do no work. Reopening catches up with the latest log.
        guard window?.isVisible == true else { return }
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: logURL.path)
            let size = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
            let identity = "\(attributes[.systemNumber] ?? ""):\(attributes[.systemFileNumber] ?? "")"
            if identity != fileIdentity || size < offset || size - offset > UInt64(readLimit) {
                fileIdentity = identity
                offset = size > UInt64(readLimit) ? size - UInt64(readLimit) : 0
                pendingUTF8.removeAll()
                showingTail = offset > 0
                discardPartialLine = offset > 0
                textView.string = ""
            }
            if size > offset {
                let handle = try FileHandle(forReadingFrom: logURL)
                defer { try? handle.close() }
                try handle.seek(toOffset: offset)
                let data = try handle.read(upToCount: readLimit) ?? Data()
                offset += UInt64(data.count)
                var bytes = data
                if discardPartialLine {
                    if let newline = bytes.firstIndex(of: 0x0a) {
                        bytes = Data(bytes.suffix(from: bytes.index(after: newline)))
                        discardPartialLine = false
                    } else {
                        // Still within a truncated long line; wait for its end.
                        updateStatus()
                        return
                    }
                }
                pendingUTF8.append(bytes)
                appendText(decodeCompleteUTF8())
            }
            updateStatus()
        } catch {
            status.stringValue = FileManager.default.fileExists(atPath: logURL.path)
                ? "Cannot read log: \(error.localizedDescription) — retrying automatically."
                : "Waiting for a log from this launcher…"
        }
    }

    private func decodeCompleteUTF8() -> String {
        // A write can stop partway through a UTF-8 character; keep that suffix
        // for the next refresh instead of displaying a replacement character.
        let bytes = [UInt8](pendingUTF8)
        var end = bytes.count
        if !bytes.isEmpty {
            var lead = bytes.count - 1
            while lead > 0 && bytes[lead] & 0xc0 == 0x80 { lead -= 1 }
            let first = bytes[lead]
            let expected = first & 0xf8 == 0xf0 ? 4 : first & 0xf0 == 0xe0 ? 3 : first & 0xe0 == 0xc0 ? 2 : 1
            if bytes.count - lead < expected { end = lead }
        }
        let result = String(decoding: bytes.prefix(end), as: UTF8.self)
        pendingUTF8 = Data(bytes.suffix(bytes.count - end))
        return result
    }

    private func appendText(_ text: String) {
        guard !text.isEmpty, let storage = textView.textStorage else { return }
        let previousOrigin = scrollView.contentView.bounds.origin
        storage.beginEditing()
        storage.append(NSAttributedString(string: text, attributes: [
            .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .regular),
            .foregroundColor: NSColor.textColor
        ]))
        // Keep the viewer bounded too, even during very verbose calculations.
        if storage.length > displayLimit {
            let value = storage.string as NSString
            var count = storage.length - displayLimit
            let newline = value.range(of: "\n", range: NSRange(location: count, length: storage.length - count))
            if newline.location != NSNotFound { count = NSMaxRange(newline) }
            if count < value.length && CFStringIsSurrogateLowCharacter(value.character(at: count)) { count += 1 }
            storage.deleteCharacters(in: NSRange(location: 0, length: count))
            showingTail = true
        }
        storage.endEditing()
        if follow.state == .on {
            textView.scrollRangeToVisible(NSRange(location: storage.length, length: 0))
        } else {
            scrollView.contentView.scroll(to: previousOrigin)
            scrollView.reflectScrolledClipView(scrollView.contentView)
        }
    }

    private func updateStatus() {
        let scope = showingTail ? "Showing recent log output" : "Showing current log"
        status.stringValue = "Live · \(scope) · " + (follow.state == .on ? "Auto-scroll on" : "Auto-scroll paused; new messages still arrive")
    }

    @objc private func followChanged() {
        if follow.state == .on { jumpToLatest() }
        updateStatus()
    }

    @objc private func jumpToLatest() {
        follow.state = .on
        textView.scrollRangeToVisible(NSRange(location: textView.textStorage?.length ?? 0, length: 0))
        updateStatus()
    }

    @objc private func copyLog() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(textView.string, forType: .string)
    }
}

final class LauncherDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var window: NSWindow!
    private let status = NSTextField(wrappingLabelWithString: "Starting Workbench…")
    private let progress = NSProgressIndicator()
    private let browserButton = NSButton(title: "Open Workbench", target: nil, action: nil)
    private let logButton = NSButton(title: "View log", target: nil, action: nil)
    private let powerButton = NSButton(title: "Stop", target: nil, action: nil)
    private var process: Process?
    private var processGroup: pid_t?
    private var rootExited = false
    private var exitCode: Int32 = 0
    private var stopping = false
    private var quitting = false
    private var stopDeadline: Date?
    private var forcedStop = false
    private var output: FileHandle?
    private var reader: FileHandle?
    private var input: FileHandle?
    private var timer: Timer?
    private var pendingText = ""
    private var browserURL: URL?
    private var liveLog: LiveLogWindowController?
    private let launcher = Bundle.main.object(forInfoDictionaryKey: "WorkbenchLauncherPath") as? String ?? ""
    private let logDirectory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/Tensile Workbench", isDirectory: true)
    private var logURL: URL { logDirectory.appendingPathComponent("launcher.log") }

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        timer = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.poll()
        }
        RunLoop.main.add(timer!, forMode: .common)
        startServer()
    }

    private func buildMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        menu.addItem(appItem)
        let appMenu = NSMenu(title: "Tensile Workbench")
        appItem.submenu = appMenu
        for (title, action, key) in [
            ("Show launcher", #selector(showWindow), "l"),
            ("Open Workbench", #selector(openBrowser), "o"),
            ("View log", #selector(viewLog), "")
        ] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
            item.target = self
            appMenu.addItem(item)
        }
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Tensile Workbench", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem()
        menu.addItem(editItem)
        let editMenu = NSMenu(title: "Edit")
        editItem.submenu = editMenu
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        NSApp.mainMenu = menu
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 275),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Tensile Workbench"
        window.isReleasedWhenClosed = false
        window.delegate = self
        let title = NSTextField(labelWithString: "Tensile Workbench")
        title.font = .systemFont(ofSize: 23, weight: .semibold)
        let icon = NSImageView(image: NSApp.applicationIconImage)
        icon.widthAnchor.constraint(equalToConstant: 52).isActive = true
        icon.heightAnchor.constraint(equalToConstant: 52).isActive = true
        let heading = NSStackView(views: [icon, title])
        heading.orientation = .horizontal
        heading.alignment = .centerY
        heading.spacing = 14
        progress.style = .spinning
        progress.controlSize = .small
        progress.isDisplayedWhenStopped = false
        status.font = .systemFont(ofSize: 13)
        let stateRow = NSStackView(views: [progress, status])
        stateRow.orientation = .horizontal
        stateRow.alignment = .centerY
        stateRow.spacing = 10
        status.widthAnchor.constraint(equalToConstant: 420).isActive = true
        for button in [browserButton, logButton, powerButton] {
            button.bezelStyle = .rounded
            button.target = self
        }
        browserButton.action = #selector(openBrowser)
        logButton.action = #selector(viewLog)
        powerButton.action = #selector(toggleServer)
        let buttons = NSStackView(views: [browserButton, logButton, powerButton])
        buttons.orientation = .horizontal
        buttons.spacing = 10
        let help = NSTextField(wrappingLabelWithString:
            "Closing this window leaves Workbench running in the Dock. Quit the app to stop its server.")
        help.font = .systemFont(ofSize: 11)
        help.textColor = .secondaryLabelColor
        let stack = NSStackView(views: [heading, stateRow, buttons, help])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 18
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 22),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: window.contentView!.bottomAnchor, constant: -20)
        ])
        window.center()
        showWindow()
    }

    @objc private func showWindow() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    private func existingServer() throws -> Bool {
        let query = Process()
        query.executableURL = URL(fileURLWithPath: "/bin/ps")
        query.arguments = ["-axo", "command="]
        let pipe = Pipe()
        query.standardOutput = pipe
        query.standardError = FileHandle.nullDevice
        try query.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        query.waitUntilExit()
        guard query.terminationStatus == 0 else {
            throw NSError(domain: "WorkbenchLauncher", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Couldn't check for an existing Workbench server."])
        }
        let serverPath = URL(fileURLWithPath: launcher).deletingLastPathComponent()
            .appendingPathComponent("workbench_server.py").path
        return String(decoding: data, as: UTF8.self).split(separator: "\n").contains { $0.contains(serverPath) }
    }

    private func prepareLog() throws {
        liveLog?.invalidateFile()
        let fm = FileManager.default
        try fm.createDirectory(at: logDirectory, withIntermediateDirectories: true,
                               attributes: [.posixPermissions: 0o700])
        if fm.fileExists(atPath: logURL.path) {
            let previous = logDirectory.appendingPathComponent("launcher.previous.log")
            if fm.fileExists(atPath: previous.path) { try fm.removeItem(at: previous) }
            try fm.moveItem(at: logURL, to: previous)
        }
        let descriptor = Darwin.open(logURL.path, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0o600)
        guard descriptor >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        output = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        reader = try FileHandle(forReadingFrom: logURL)
    }

    private func startServer() {
        guard process == nil else { return }
        browserURL = nil
        browserButton.isEnabled = false
        powerButton.isEnabled = false
        logButton.isEnabled = FileManager.default.fileExists(atPath: logURL.path)
        status.stringValue = "Starting Workbench…"
        progress.startAnimation(nil)
        do {
            guard FileManager.default.isReadableFile(atPath: launcher) else {
                throw NSError(domain: "WorkbenchLauncher", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Workbench folder not found. If you moved it, run Install_Tensile_Workbench_App.command from its new location."])
            }
            if try existingServer() {
                status.stringValue = "Workbench is already running outside this app. If it is open in Terminal, press Ctrl+C there, then click Start here."
                powerButton.title = "Start"
                powerButton.isEnabled = true
                progress.stopAnimation(nil)
                return
            }
            try prepareLog()
            let child = Process()
            child.executableURL = Bundle.main.executableURL!
            child.arguments = ["--server-child", launcher]
            child.currentDirectoryURL = URL(fileURLWithPath: launcher).deletingLastPathComponent()
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            if let environmentPath = Bundle.main.object(forInfoDictionaryKey: "WorkbenchEnvironmentPath") as? String,
               !environmentPath.isEmpty {
                environment["TENSILE_ENV_DIR"] = environmentPath
            }
            environment["TENSILE_DESKTOP_APP"] = "1"
            child.environment = environment
            input = try FileHandle(forReadingFrom: URL(fileURLWithPath: "/dev/null"))
            child.standardInput = input
            child.standardOutput = output
            child.standardError = output
            child.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    self?.rootExited = true
                    self?.exitCode = finished.terminationStatus
                    self?.poll()
                }
            }
            rootExited = false
            stopping = false
            forcedStop = false
            pendingText = ""
            try child.run()
            process = child
            processGroup = child.processIdentifier
            powerButton.title = "Stop"
            powerButton.isEnabled = true
            logButton.isEnabled = true
        } catch {
            finishHandles()
            status.stringValue = "Could not start: \(error.localizedDescription)"
            powerButton.title = "Start"
            powerButton.isEnabled = true
            progress.stopAnimation(nil)
        }
    }

    private func poll() {
        defer { liveLog?.refresh() }
        guard process != nil else { return }
        do {
            // Keep logs bounded; O_APPEND keeps child writers correct after truncation.
            let size = (try FileManager.default.attributesOfItem(atPath: logURL.path)[.size] as? NSNumber)?.intValue ?? 0
            if size > 10 * 1024 * 1024 {
                try output?.truncate(atOffset: 0)
                try reader?.seek(toOffset: 0)
                pendingText = ""
                liveLog?.invalidateFile()
            }
            if let data = try reader?.readToEnd(), !data.isEmpty {
                pendingText += String(decoding: data, as: UTF8.self)
                // Only accept this launch's loopback URL. Keep the token out of status text.
                let pattern = #"http://127\.0\.0\.1:[0-9]+/[^\s\u001B]*(?=\s)"#
                if browserURL == nil, let range = pendingText.range(of: pattern, options: .regularExpression),
                   let url = URL(string: String(pendingText[range])), url.host == "127.0.0.1" {
                    browserURL = url
                    if !stopping {
                        status.stringValue = "Server running. Workbench opens in your browser."
                        browserButton.isEnabled = true
                        progress.stopAnimation(nil)
                    }
                }
                pendingText = String(pendingText.suffix(65536))
            }
        } catch {
            // The server can continue if log viewing fails; stop/quit stay available.
        }
        let groupAlive = processGroup.map { kill(-$0, 0) == 0 || errno == EPERM } ?? false
        if rootExited && !groupAlive {
            let wasStopping = stopping
            process = nil
            processGroup = nil
            stopping = false
            browserURL = nil
            browserButton.isEnabled = false
            powerButton.title = "Start"
            powerButton.isEnabled = true
            progress.stopAnimation(nil)
            finishHandles()
            status.stringValue = wasStopping ? "Workbench stopped. Click Start when you need it again." :
                "Workbench exited (code \(exitCode)). View the log for details."
            if quitting { NSApp.reply(toApplicationShouldTerminate: true) }
        } else if rootExited && !stopping {
            requestStop()
        } else if stopping, let deadline = stopDeadline, Date() > deadline, !forcedStop {
            forcedStop = true
            status.stringValue = "Finishing shutdown…"
            if let group = processGroup { _ = kill(-group, SIGKILL) }
        }
    }

    private func finishHandles() {
        try? reader?.close()
        try? output?.close()
        try? input?.close()
        reader = nil
        output = nil
        input = nil
    }

    @objc private func openBrowser() {
        if let url = browserURL, !stopping { NSWorkspace.shared.open(url) }
        else { showWindow() }
    }

    @objc private func viewLog() {
        if liveLog == nil { liveLog = LiveLogWindowController(logURL: logURL) }
        liveLog?.open()
    }

    private func confirmStop(quitting: Bool) -> Bool {
        let alert = NSAlert()
        alert.messageText = quitting ? "Quit and stop Workbench?" : "Stop Workbench?"
        alert.informativeText = "This stops the server started by this app and any running calculations. Saved settings and source data are kept."
        alert.addButton(withTitle: quitting ? "Quit and stop" : "Stop")
        alert.addButton(withTitle: "Cancel")
        return alert.runModal() == .alertFirstButtonReturn
    }

    private func requestStop() {
        guard let child = process, !stopping else { return }
        stopping = true
        stopDeadline = Date().addingTimeInterval(20)
        browserButton.isEnabled = false
        powerButton.isEnabled = false
        status.stringValue = "Stopping Workbench and closing its calculation session…"
        progress.startAnimation(nil)
        // Voilà handles SIGTERM by closing its kernels; allow that cleanup to finish.
        if let group = processGroup, kill(-group, SIGTERM) == -1, child.isRunning { child.terminate() }
    }

    @objc private func toggleServer() {
        if process == nil { startServer() }
        else if !stopping && confirmStop(quitting: false) { requestStop() }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard process != nil else { return .terminateNow }
        if quitting { return .terminateLater }
        if !stopping && !confirmStop(quitting: true) { return .terminateCancel }
        quitting = true
        requestStop()
        return .terminateLater
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.regular)
let delegate = LauncherDelegate()
application.delegate = delegate
application.run()
