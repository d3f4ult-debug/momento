import 'package:flutter/material.dart';
import 'config/app_config.dart';
import 'screens/dashboard_screen.dart';
import 'services/bridge_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final bridgeService = BridgeService();

  runApp(MomentoDesktopApp(bridgeService: bridgeService));
}

class MomentoDesktopApp extends StatelessWidget {
  final BridgeService bridgeService;

  const MomentoDesktopApp({
    super.key,
    required this.bridgeService,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appTitle,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      home: DashboardScreen(bridgeService: bridgeService),
    );
  }
}
