import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:momento_desktop/main.dart';
import 'package:momento_desktop/services/bridge_service.dart';

void main() {
  testWidgets('Momento Desktop app initializes and displays workspace', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockBridge = BridgeService();

    await tester.pumpWidget(MomentoDesktopApp(bridgeService: mockBridge));
    await tester.pump();

    // Verify brand and workspace header are rendered
    expect(find.text('Momento'), findsOneWidget);
    expect(find.text('Natural Language Execution Workspace'), findsOneWidget);
    expect(find.text('EXECUTION TARGET'), findsOneWidget);
  });
}
