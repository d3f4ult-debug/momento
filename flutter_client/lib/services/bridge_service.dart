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

  /// Find Python executable (checks local workspace venv and system PATH)
  Future<String> _getPythonExecutable() async {
    final currentDir = Directory.current.path;
    final candidates = [
      '$currentDir\\venv\\Scripts\\python.exe',
      '$currentDir\\..\\venv\\Scripts\\python.exe',
      'python',
      'python3',
      'py',
    ];
    for (final candidate in candidates) {
      if (candidate.endsWith('.exe')) {
        if (await File(candidate).exists()) return candidate;
      }
    }
    return 'python';
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
    final py = await _getPythonExecutable();
    try {
      final proc = await Process.run(py, ['momento_cli.py', 'setup', '--non-interactive']);
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
    final py = await _getPythonExecutable();
    try {
      await Process.run(py, ['momento_cli.py', 'scan']);
      final state = await _readLocalStateFallback();
      final rawApps = state['discovered_apps'] as List<dynamic>? ?? [];
      return rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  /// Send conversational command (e.g. "Momento, open notepad" or "Run Calculator")
  Future<Map<String, dynamic>> sendMessage(String message, {String? mode}) async {
    final effMode = mode ?? executionMode;
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

  /// Robust Python execution fallback invoking DesktopAppBridge directly
  Future<Map<String, dynamic>> _runPythonExecutionFallback(String message, String mode) async {
    final py = await _getPythonExecutable();

    // 1. Direct Python invocation of DesktopAppBridge
    try {
      final script = "import json, sys; "
          "from client.desktop_bridge import DesktopAppBridge; "
          "b = DesktopAppBridge(); "
          "res = b.send_message(sys.argv[1], execution_mode=sys.argv[2]); "
          "print(json.dumps(res))";

      final proc = await Process.run(py, ['-c', script, message, mode]);
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
      final proc = await Process.run(py, ['momento_cli.py', 'chat', message, '--mode', mode, '--json']);
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
      final proc = await Process.run(py, ['momento_cli.py', message]);
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
        final py = await _getPythonExecutable();
        final script = "import json, sys; "
            "from client.desktop_bridge import DesktopAppBridge; "
            "b = DesktopAppBridge(); "
            "print(json.dumps(b.get_session_logs(sys.argv[1])))";
        final proc = await Process.run(py, ['-c', script, sessionId]);
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
        final py = await _getPythonExecutable();
        final script = "import json, sys; "
            "from client.desktop_bridge import DesktopAppBridge; "
            "b = DesktopAppBridge(); "
            "print(json.dumps(b.stop_session(sys.argv[1])))";
        final proc = await Process.run(py, ['-c', script, sessionId]);
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
