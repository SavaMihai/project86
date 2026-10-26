import XCTest

final class Project86UITests: XCTestCase {
    @MainActor func testRealDOSInNativeWindow() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--fresh-dos"]
        app.launch()
        let display = app.textViews["dos-screen"]
        XCTAssertTrue(display.waitForExistence(timeout: 15))
        let ready = NSPredicate(format: "value CONTAINS %@", "MS-DOS Version 4.00")
        expectation(for: ready, evaluatedWith: display)
        waitForExpectations(timeout: 15)
        display.click()
        display.typeText("ver\r")
        expectation(for: NSPredicate(format: "value CONTAINS %@", "MS-DOS Version 4.00"), evaluatedWith: display)
        waitForExpectations(timeout: 15)
        display.typeText("echo MAC-WINDOW-OK\r")
        expectation(for: NSPredicate(format: "value CONTAINS %@", "MAC-WINDOW-OK"), evaluatedWith: display)
        waitForExpectations(timeout: 10)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Project86-Mac-real-DOS"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}
