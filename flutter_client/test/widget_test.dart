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

  testWidgets('Teach Custom App button opens RegisterAppDialog', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockBridge = BridgeService();

    await tester.pumpWidget(MomentoDesktopApp(bridgeService: mockBridge));
    await tester.pump();

    final teachButton = find.text('+ Teach Custom App');
    expect(teachButton, findsOneWidget);

    await tester.tap(teachButton);
    await tester.pumpAndSettle();

    expect(find.text('Teach Momento App'), findsOneWidget);
    expect(find.text('Application Name *'), findsOneWidget);
    expect(find.text('Executable / Binary Path *'), findsOneWidget);
    expect(find.text('Working Directory (Optional)'), findsOneWidget);
    expect(find.text('Arguments / Data File Path (Optional)'), findsOneWidget);
  });

  testWidgets('Profile & Learn App button opens profiling dialog', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockBridge = BridgeService();

    await tester.pumpWidget(MomentoDesktopApp(bridgeService: mockBridge));
    await tester.pump();

    final profileButton = find.text('⚡ Profile & Learn App');
    expect(profileButton, findsOneWidget);

    await tester.tap(profileButton);
    await tester.pumpAndSettle();

    expect(find.text('Reverse-Engineer & Profile App'), findsOneWidget);
    expect(find.text('Profile App'), findsOneWidget);
  });

  testWidgets('TargetPickerDropZone renders visual drop zone and Pick Window button', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockBridge = BridgeService();

    await tester.pumpWidget(MomentoDesktopApp(bridgeService: mockBridge));
    await tester.pump();

    final teachButton = find.text('+ Teach Custom App');
    await tester.tap(teachButton);
    await tester.pumpAndSettle();

    // Verify visual target picker elements inside RegisterAppDialog
    expect(find.text('Visual Target Picker & Drop Zone'), findsOneWidget);
    expect(find.text('Pick Window'), findsOneWidget);
    expect(find.byIcon(Icons.gps_fixed_rounded), findsOneWidget);
  });
}

