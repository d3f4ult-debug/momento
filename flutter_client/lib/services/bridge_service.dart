import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import '../models/app_info.dart';

class BridgeService {
  String backendUrl;
  String executionMode;
  bool isSetupCompleted = false;

  BridgeService({
    String? initialUrl,
    String? initialMode,
  })  : backendUrl = (initialUrl != null && initialUrl.endsWith('/'))
            ? initialUrl.substring(0, initialUrl.length - 1)
            : (initialUrl ?? AppConfig.defaultVpsUrl),
        executionMode = initialMode ?? AppConfig.modeHybrid;

  String _cleanUrl(String url) => url.endsWith('/') ? url.substring(0, url.length - 1) : url;

  bool _isDaemonStarting = false;

  /// Locate the Momento project root directory containing momento_cli.py and client/
  Directory? findProjectRoot() {
    // 1. Check explicit environment override
    final envRoot = Platform.environment['MOMENTO_PROJECT_ROOT'];
    if (envRoot != null && envRoot.trim().isNotEmpty) {
      final dir = Directory(envRoot.trim());
      if (dir.existsSync()) return dir;
    }

    // 2. Candidate starting directories: executable directory and working directory
    final startingDirs = <Directory>[];
    try {
      final exe = File(Platform.resolvedExecutable);
      startingDirs.add(exe.parent);
    } catch (_) {}
    startingDirs.add(Directory.current);

    // 3. Traverse upwards looking for project markers
    for (final start in startingDirs) {
      var current = start.absolute;
      for (int i = 0; i < 8; i++) {
        final cliFile = File('${current.path}${Platform.pathSeparator}momento_cli.py');
        final bridgeFile = File('${current.path}${Platform.pathSeparator}client${Platform.pathSeparator}bridge_server.py');
        if (cliFile.existsSync() || bridgeFile.existsSync()) {
          return current;
        }
        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    }
    return null;
  }

  /// Find Python executable (checks local workspace venv and system PATH)
  Future<String> getPythonExecutable() async {
    final root = findProjectRoot();
    final candidates = <String>[];

    if (root != null) {
      if (Platform.isWindows) {
        candidates.add('${root.path}\\venv\\Scripts\\python.exe');
        candidates.add('${root.path}\\.venv\\Scripts\\python.exe');
      } else {
        candidates.add('${root.path}/venv/bin/python');
        candidates.add('${root.path}/.venv/bin/python');
      }
    }

    final currentDir = Directory.current.path;
    if (Platform.isWindows) {
      candidates.add('$currentDir\\venv\\Scripts\\python.exe');
      candidates.add('$currentDir\\..\\venv\\Scripts\\python.exe');
    } else {
      candidates.add('$currentDir/venv/bin/python');
      candidates.add('$currentDir/../venv/bin/python');
    }

    for (final candidate in candidates) {
      if (await File(candidate).exists()) return candidate;
    }

    return Platform.isWindows ? 'python' : 'python3';
  }

  /// Get environment variables with PYTHONPATH pointing to project root
  Map<String, String> _getPythonEnvironment(Directory? root) {
    final env = Map<String, String>.from(Platform.environment);
    if (root != null) {
      env['PYTHONPATH'] = root.path;
      env['MOMENTO_PROJECT_ROOT'] = root.path;
    }
    return env;
  }

  /// Get absolute path to momento_cli.py
  String _getMomentoCliPath(Directory? root) {
    if (root != null) {
      final cli = File('${root.path}${Platform.pathSeparator}momento_cli.py');
      if (cli.existsSync()) return cli.path;
    }
    return 'momento_cli.py';
  }

  /// Run Python subprocess with project root working directory and environment
  Future<ProcessResult> runPythonProcess(
    String py,
    List<String> args,
  ) async {
    final root = findProjectRoot();
    final workingDir = root?.path ?? Directory.current.path;
    final env = _getPythonEnvironment(root);
    return Process.run(
      py,
      args,
      workingDirectory: workingDir,
      environment: env,
    );
  }

  /// Check if the local bridge server HTTP daemon is currently responding
  Future<bool> isDaemonRunning() async {
    for (final url in ['http://127.0.0.1:8000', 'http://localhost:8000']) {
      try {
        final res = await http.get(
          Uri.parse('$url/api/client/state'),
          headers: {'Accept': 'application/json'},
        ).timeout(const Duration(milliseconds: 600));
        if (res.statusCode == 200) return true;
      } catch (_) {}
    }
    return false;
  }

  /// Ensure the Python bridge server daemon is running, spinning it up if necessary
  Future<bool> ensureDaemonRunning() async {
    if (await isDaemonRunning()) return true;

    if (_isDaemonStarting) {
      for (int i = 0; i < 10; i++) {
        await Future.delayed(const Duration(milliseconds: 250));
        if (await isDaemonRunning()) return true;
      }
      return false;
    }

    _isDaemonStarting = true;
    try {
      final root = findProjectRoot();
      final py = await getPythonExecutable();
      final bridgeScript = root != null
          ? '${root.path}${Platform.pathSeparator}client${Platform.pathSeparator}bridge_server.py'
          : 'client/bridge_server.py';

      final workingDir = root?.path ?? Directory.current.path;
      final env = _getPythonEnvironment(root);
      env['MOMENTO_BRIDGE_PORT'] = '8000';

      debugPrint('[BridgeService] Spinning up background Python bridge daemon: $py $bridgeScript (cwd: $workingDir)');

      await Process.start(
        py,
        [bridgeScript],
        workingDirectory: workingDir,
        environment: env,
        mode: ProcessStartMode.detached,
      );

      // Poll until the daemon is online or timeout (up to 4.5 seconds)
      for (int i = 0; i < 15; i++) {
        await Future.delayed(const Duration(milliseconds: 300));
        if (await isDaemonRunning()) {
          debugPrint('[BridgeService] Connected to background bridge daemon at http://127.0.0.1:8000');
          return true;
        }
      }
    } catch (e) {
      debugPrint('[BridgeService] Error starting background daemon: $e');
    } finally {
      _isDaemonStarting = false;
    }

    return await isDaemonRunning();
  }

  /// Get ordered list of candidate URLs for given execution mode
  List<String> _getCandidateUrls({String? mode}) {
    final effMode = mode ?? executionMode;
    final cleanBack = _cleanUrl(backendUrl);
    final urls = <String>[];

    if (effMode == AppConfig.modeLocal || effMode.toLowerCase().contains('local')) {
      urls.add('http://localhost:8000');
      urls.add(AppConfig.defaultLocalUrl);
      if (!urls.contains(cleanBack)) urls.add(cleanBack);
    } else if (effMode == AppConfig.modeHybrid) {
      if (!urls.contains(cleanBack)) urls.add(cleanBack);
      urls.add('http://localhost:8000');
      urls.add(AppConfig.defaultLocalUrl);
    } else {
      urls.add(cleanBack);
      urls.add('http://localhost:8000');
      urls.add(AppConfig.defaultLocalUrl);
    }
    return urls;
  }

  /// Fetch initial state: setup status, permissions, discovered apps, active sessions
  Future<Map<String, dynamic>> fetchInitialState() async {
    // Automatically ensure background daemon is running for local/hybrid workflow
    if (executionMode == AppConfig.modeLocal || executionMode == AppConfig.modeHybrid) {
      await ensureDaemonRunning();
    }

    final urls = _getCandidateUrls();
    for (final url in urls) {
      try {
        final res = await http.get(
          Uri.parse('$url/api/client/state'),
          headers: {'Accept': 'application/json'},
        ).timeout(const Duration(seconds: 3));

        if (res.statusCode == 200) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          isSetupCompleted = data['setup_completed'] ?? false;
          return data;
        }
      } catch (_) {}
    }

    // Offline / Local File Fallback
    return _readLocalStateFallback();
  }

  /// Read local config and registry from ~/.momento directly as a fallback
  Future<Map<String, dynamic>> _readLocalStateFallback() async {
    final home = Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '';
    final momentoDir = Directory('$home/.momento');
    final configFile = File('${momentoDir.path}/config.json');
    final registryFile = File('${momentoDir.path}/registry.json');

    bool setupDone = false;
    List<dynamic> appsList = [];

    if (await configFile.exists()) {
      try {
        final cfgContent = await configFile.readAsString();
        final cfg = jsonDecode(cfgContent);
        setupDone = cfg['setup_completed'] ?? false;
        backendUrl = cfg['backend_url'] ?? backendUrl;
        isSetupCompleted = setupDone;
      } catch (_) {}
    }

    if (await registryFile.exists()) {
      try {
        final regContent = await registryFile.readAsString();
        final reg = jsonDecode(regContent);
        final appsMap = reg['apps'] as Map<String, dynamic>? ?? {};
        appsList = appsMap.values.toList();
      } catch (_) {}
    }

    return {
      'setup_completed': setupDone,
      'backend_url': backendUrl,
      'execution_mode': executionMode,
      'discovered_apps': appsList,
      'total_apps': appsList.length,
      'active_sessions': <dynamic>[],
    };
  }

  /// Grant system permissions and run initial scan
  Future<Map<String, dynamic>> grantPermissions({
    bool filesystem = true,
    bool discovery = true,
    bool execution = true,
    String? newBackendUrl,
  }) async {
    if (newBackendUrl != null && newBackendUrl.trim().isNotEmpty) {
      backendUrl = _cleanUrl(newBackendUrl.trim());
    }

    if (executionMode == AppConfig.modeLocal || executionMode == AppConfig.modeHybrid) {
      await ensureDaemonRunning();
    }

    final urls = _getCandidateUrls();
    for (final url in urls) {
      try {
        final res = await http.post(
          Uri.parse('$url/api/client/permissions'),
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: jsonEncode({
            'filesystem': filesystem,
            'discovery': discovery,
            'execution': execution,
            'backend_url': backendUrl,
          }),
        ).timeout(const Duration(seconds: 10));

        if (res.statusCode == 200) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          isSetupCompleted = true;
          return data;
        }
      } catch (_) {}
    }

    // Fallback: execute local python CLI onboarding
    return _runLocalScannerFallback();
  }

  /// Run local Python scanner fallback
  Future<Map<String, dynamic>> _runLocalScannerFallback() async {
    final py = await getPythonExecutable();
    final root = findProjectRoot();
    final cli = _getMomentoCliPath(root);
    try {
      final proc = await runPythonProcess(py, [cli, 'setup', '--non-interactive']);
      if (proc.exitCode == 0) {
        isSetupCompleted = true;
        final state = await _readLocalStateFallback();
        return {
          'success': true,
          'setup_completed': true,
          'total_apps': state['total_apps'],
          'apps': state['discovered_apps'],
        };
      }
    } catch (_) {}

    isSetupCompleted = true;
    return {'success': true, 'setup_completed': true, 'total_apps': 0, 'apps': []};
  }

  /// Rescan applications
  Future<List<AppInfo>> rescanApps() async {
    if (executionMode == AppConfig.modeLocal || executionMode == AppConfig.modeHybrid) {
      await ensureDaemonRunning();
    }

    final urls = _getCandidateUrls();
    for (final url in urls) {
      try {
        final res = await http.post(
          Uri.parse('$url/api/client/scan'),
          headers: {'Accept': 'application/json'},
        ).timeout(const Duration(seconds: 10));

        if (res.statusCode == 200) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          final rawApps = data['apps'] as List<dynamic>? ?? [];
          return rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
        }
      } catch (_) {}
    }

    // Fallback
    final py = await getPythonExecutable();
    final root = findProjectRoot();
    final cli = _getMomentoCliPath(root);
    try {
      await runPythonProcess(py, [cli, 'scan']);
      final state = await _readLocalStateFallback();
      final rawApps = state['discovered_apps'] as List<dynamic>? ?? [];
      return rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  /// Manually register a custom application into the local registry
  Future<Map<String, dynamic>> registerApp({
    required String name,
    required String binaryPath,
    List<String>? aliases,
    String? category,
    String? workingDir,
    String? arguments,
    String? dataFilePath,
  }) async {
    if (executionMode == AppConfig.modeLocal || executionMode == AppConfig.modeHybrid) {
      await ensureDaemonRunning();
    }

    final urls = _getCandidateUrls();
    for (final url in urls) {
      try {
        final res = await http.post(
          Uri.parse('$url/api/client/apps/register'),
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: jsonEncode({
            'name': name.trim(),
            'binary_path': binaryPath.trim(),
            if (aliases != null && aliases.isNotEmpty) 'aliases': aliases,
            'category': category ?? 'custom',
            if (workingDir != null && workingDir.trim().isNotEmpty) 'working_dir': workingDir.trim(),
            if (arguments != null && arguments.trim().isNotEmpty) 'args': arguments.trim(),
            if (dataFilePath != null && dataFilePath.trim().isNotEmpty) 'data_file_path': dataFilePath.trim(),
          }),
        ).timeout(const Duration(seconds: 10));

        if (res.statusCode == 200 || res.statusCode == 400) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          return data;
        }
      } catch (_) {}
    }

    // CLI fallback for custom app registration
    final py = await getPythonExecutable();
    final root = findProjectRoot();
    final cli = _getMomentoCliPath(root);
    try {
      final args = [cli, 'register', name.trim(), binaryPath.trim(), '--json'];
      if (aliases != null && aliases.isNotEmpty) {
        args.add('--aliases');
        args.addAll(aliases);
      }
      if (workingDir != null && workingDir.trim().isNotEmpty) {
        args.addAll(['--working-dir', workingDir.trim()]);
      }
      if (arguments != null && arguments.trim().isNotEmpty) {
        args.addAll(['--args', arguments.trim()]);
      }
      if (dataFilePath != null && dataFilePath.trim().isNotEmpty) {
        args.addAll(['--data-file', dataFilePath.trim()]);
      }
      final proc = await runPythonProcess(py, args);
      final out = proc.stdout.toString().trim();
      if (out.isNotEmpty) {
        return jsonDecode(out) as Map<String, dynamic>;
      }
    } catch (e) {
      debugPrint('[BridgeService] CLI register fallback error: $e');
    }

    return {
      'success': false,
      'error': 'Failed to register application. Check if Python backend is available.',
    };
  }

  /// Send conversational command (e.g. "Momento, open notepad" or "Run Calculator")
  Future<Map<String, dynamic>> sendMessage(String message, {String? mode}) async {
    final effMode = mode ?? executionMode;
    if (effMode == AppConfig.modeLocal || effMode == AppConfig.modeHybrid) {
      await ensureDaemonRunning();
    }

    final urls = _getCandidateUrls(mode: effMode);

    for (final url in urls) {
      try {
        final res = await http.post(
          Uri.parse('$url/api/client/chat'),
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: jsonEncode({
            'message': message,
            'execution_mode': effMode,
          }),
        ).timeout(const Duration(seconds: 10));

        if (res.statusCode == 200 || res.statusCode == 400) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          return data;
        }
      } catch (e) {
        debugPrint('[BridgeService] Chat HTTP to $url error: $e');
      }
    }

    // Python Direct DesktopAppBridge Fallback
    return _runPythonExecutionFallback(message, effMode);
  }

  /// Robust Python execution fallback invoking DesktopAppBridge directly with absolute paths & working directory
  Future<Map<String, dynamic>> _runPythonExecutionFallback(String message, String mode) async {
    final py = await getPythonExecutable();
    final root = findProjectRoot();
    final cli = _getMomentoCliPath(root);

    // 1. Direct Python invocation of DesktopAppBridge
    try {
      final script = "import json, sys; "
          "from client.desktop_bridge import DesktopAppBridge; "
          "b = DesktopAppBridge(); "
          "res = b.send_message(sys.argv[1], execution_mode=sys.argv[2]); "
          "print(json.dumps(res))";

      final proc = await runPythonProcess(py, ['-c', script, message, mode]);
      final out = proc.stdout.toString().trim();
      if (out.isNotEmpty) {
        try {
          final data = jsonDecode(out) as Map<String, dynamic>;
          return data;
        } catch (_) {}
      }
    } catch (e) {
      debugPrint('[BridgeService] Python direct bridge execution failed: $e');
    }

    // 2. Fallback to momento_cli.py chat command
    try {
      final proc = await runPythonProcess(py, [cli, 'chat', message, '--mode', mode, '--json']);
      final out = proc.stdout.toString().trim();
      if (out.isNotEmpty) {
        try {
          final data = jsonDecode(out) as Map<String, dynamic>;
          return data;
        } catch (_) {}
      }
    } catch (_) {}

    // 3. Fallback to generic command execution
    try {
      final proc = await runPythonProcess(py, [cli, message]);
      final out = proc.stdout.toString().trim();
      final err = proc.stderr.toString().trim();
      final msg = out.isNotEmpty ? out : err;
      return {
        'success': proc.exitCode == 0,
        'action': 'cli_fallback',
        'message': msg.isNotEmpty ? msg : 'Command processed with exit code ${proc.exitCode}.',
      };
    } catch (err) {
      return {
        'success': false,
        'action': 'error',
        'message': 'Failed to execute command: $err. Check if backend is running.',
      };
    }
  }

  /// Get live logs for an execution session
  Future<Map<String, dynamic>> getSessionLogs(String sessionId) async {
    final isLocal = sessionId.startsWith('sbx_local_') || executionMode == AppConfig.modeLocal;
    final urls = isLocal
        ? ['http://localhost:8000', AppConfig.defaultLocalUrl, _cleanUrl(backendUrl)]
        : [_cleanUrl(backendUrl), 'http://localhost:8000', AppConfig.defaultLocalUrl];

    for (final url in urls) {
      try {
        final res = await http.get(
          Uri.parse('$url/api/client/logs/$sessionId'),
          headers: {'Accept': 'application/json'},
        ).timeout(const Duration(seconds: 3));

        if (res.statusCode == 200) {
          return jsonDecode(res.body) as Map<String, dynamic>;
        }
      } catch (_) {}
    }

    // Python direct fallback for local session logs
    if (sessionId.startsWith('sbx_local_')) {
      try {
        final py = await getPythonExecutable();
        final script = "import json, sys; "
            "from client.desktop_bridge import DesktopAppBridge; "
            "b = DesktopAppBridge(); "
            "print(json.dumps(b.get_session_logs(sys.argv[1])))";
        final proc = await runPythonProcess(py, ['-c', script, sessionId]);
        final out = proc.stdout.toString().trim();
        if (out.isNotEmpty) {
          return jsonDecode(out) as Map<String, dynamic>;
        }
      } catch (_) {}
    }

    return {'success': false, 'logs': <String>[]};
  }

  /// Stop a running process session
  Future<bool> stopSession(String sessionId) async {
    final isLocal = sessionId.startsWith('sbx_local_') || executionMode == AppConfig.modeLocal;
    final urls = isLocal
        ? ['http://localhost:8000', AppConfig.defaultLocalUrl, _cleanUrl(backendUrl)]
        : [_cleanUrl(backendUrl), 'http://localhost:8000', AppConfig.defaultLocalUrl];

    for (final url in urls) {
      try {
        final res = await http.post(
          Uri.parse('$url/api/client/stop'),
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: jsonEncode({'session_id': sessionId}),
        ).timeout(const Duration(seconds: 4));

        if (res.statusCode == 200) {
          final data = jsonDecode(res.body) as Map<String, dynamic>;
          return data['success'] ?? false;
        }
      } catch (_) {}
    }

    // Python direct fallback for stopping local process
    if (sessionId.startsWith('sbx_local_')) {
      try {
        final py = await getPythonExecutable();
        final script = "import json, sys; "
            "from client.desktop_bridge import DesktopAppBridge; "
            "b = DesktopAppBridge(); "
            "print(json.dumps(b.stop_session(sys.argv[1])))";
        final proc = await runPythonProcess(py, ['-c', script, sessionId]);
        final out = proc.stdout.toString().trim();
        if (out.isNotEmpty) {
          final data = jsonDecode(out) as Map<String, dynamic>;
          return data['success'] ?? false;
        }
      } catch (_) {}
    }

    return false;
  }

  /// Save settings
  Future<bool> saveSettings({required String newUrl, required String newMode}) async {
    backendUrl = _cleanUrl(newUrl.trim());
    executionMode = newMode;
    final clean = backendUrl;

    try {
      final res = await http.post(
        Uri.parse('$clean/api/client/settings'),
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: jsonEncode({
          'backend_url': backendUrl,
          'execution_mode': executionMode,
        }),
      ).timeout(const Duration(seconds: 4));
      return res.statusCode == 200;
    } catch (_) {
      return true; // Saved in memory
    }
  }
}
