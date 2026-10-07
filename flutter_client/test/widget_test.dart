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

  testWidgets('Sidebar switches between five core engines: Maestro, Lumo, Echo, Forge, Autopilot', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockBridge = BridgeService();

    await tester.pumpWidget(MomentoDesktopApp(bridgeService: mockBridge));
    await tester.pumpAndSettle();

    // Verify 5 engine navigation buttons rendered
    expect(find.text('Maestro'), findsOneWidget);
    expect(find.text('Lumo'), findsOneWidget);
    expect(find.text('Echo'), findsOneWidget);
    expect(find.text('Forge'), findsOneWidget);
    expect(find.text('Autopilot'), findsOneWidget);

    // Switch to Lumo
    await tester.tap(find.text('Lumo'));
    await tester.pumpAndSettle();
    expect(find.text('Lumo — All-in-One Image Generation & Vision Suite'), findsOneWidget);

    // Switch to Echo
    await tester.tap(find.text('Echo'));
    await tester.pumpAndSettle();
    expect(find.text('Echo — All-in-One Audio Core'), findsOneWidget);

    // Switch to Forge
    await tester.tap(find.text('Forge'));
    await tester.pumpAndSettle();
    expect(find.text('Forge — App Builder & Zero-Vision Native Control'), findsOneWidget);

    // Switch to Autopilot
    await tester.tap(find.text('Autopilot'));
    await tester.pumpAndSettle();
    expect(find.text('Autopilot — Autonomous Background Digital Worker'), findsOneWidget);

    // Switch back to Maestro
    await tester.tap(find.text('Maestro'));
    await tester.pumpAndSettle();
    expect(find.text('Natural Language Execution Workspace'), findsOneWidget);
  });
}

