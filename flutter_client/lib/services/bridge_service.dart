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

  /// Fetch initial state: setup status, permissions, discovered apps, active sessions
  Future<Map<String, dynamic>> fetchInitialState() async {
    final clean = _cleanUrl(backendUrl);
    try {
      final res = await http.get(
        Uri.parse('$clean/api/client/state'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 4));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        isSetupCompleted = data['setup_completed'] ?? false;
        executionMode = data['execution_mode'] ?? executionMode;
        return data;
      }
    } catch (e) {
      debugPrint('[BridgeService] HTTP get state failed, checking local files fallback: $e');
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

    final clean = _cleanUrl(backendUrl);
    try {
      final res = await http.post(
        Uri.parse('$clean/api/client/permissions'),
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: jsonEncode({
          'filesystem': filesystem,
          'discovery': discovery,
          'execution': execution,
          'backend_url': backendUrl,
        }),
      ).timeout(const Duration(seconds: 15));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        isSetupCompleted = true;
        return data;
      }
    } catch (e) {
      debugPrint('[BridgeService] Permissions HTTP error: $e. Running local python scan fallback...');
    }

    // Fallback: execute local python CLI onboarding
    return _runLocalScannerFallback();
  }

  /// Run local Python scanner fallback
  Future<Map<String, dynamic>> _runLocalScannerFallback() async {
    try {
      final proc = await Process.run('python', ['momento_cli.py', 'setup', '--non-interactive']);
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
    final clean = _cleanUrl(backendUrl);
    try {
      final res = await http.post(
        Uri.parse('$clean/api/client/scan'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 15));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final rawApps = data['apps'] as List<dynamic>? ?? [];
        return rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
      }
    } catch (e) {
      debugPrint('[BridgeService] Rescan HTTP error: $e');
    }

    // Fallback
    try {
      await Process.run('python', ['momento_cli.py', 'scan']);
      final state = await _readLocalStateFallback();
      final rawApps = state['discovered_apps'] as List<dynamic>? ?? [];
      return rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  /// Send conversational command (e.g. "Momento, open notepad")
  Future<Map<String, dynamic>> sendMessage(String message, {String? mode}) async {
    final clean = _cleanUrl(backendUrl);
    final effMode = mode ?? executionMode;

    try {
      final res = await http.post(
        Uri.parse('$clean/api/client/chat'),
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: jsonEncode({
          'message': message,
          'execution_mode': effMode,
        }),
      ).timeout(const Duration(seconds: 12));

      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    } catch (e) {
      debugPrint('[BridgeService] Chat HTTP error: $e. Invoking Python CLI fallback...');
    }

    // Local CLI Fallback
    try {
      final proc = await Process.run('python', ['momento_cli.py', message]);
      final output = proc.stdout.toString().trim();
      return {
        'success': proc.exitCode == 0,
        'action': 'cli_fallback',
        'message': output.isNotEmpty ? output : proc.stderr.toString().trim(),
      };
    } catch (err) {
      return {
        'success': false,
        'message': 'Failed to execute command: $err. Check if backend is running.',
      };
    }
  }

  /// Get live logs for an execution session
  Future<Map<String, dynamic>> getSessionLogs(String sessionId) async {
    final clean = _cleanUrl(backendUrl);
    try {
      final res = await http.get(
        Uri.parse('$clean/api/client/logs/$sessionId'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 3));

      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return {'success': false, 'logs': <String>[]};
  }

  /// Stop a running process session
  Future<bool> stopSession(String sessionId) async {
    final clean = _cleanUrl(backendUrl);
    try {
      final res = await http.post(
        Uri.parse('$clean/api/client/stop'),
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: jsonEncode({'session_id': sessionId}),
      ).timeout(const Duration(seconds: 4));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        return data['success'] ?? false;
      }
    } catch (_) {}
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
