from psk.git_tui.app import GitTuiApp


def run_app(base_branch: str = "main") -> None:
    app = GitTuiApp(base_branch=base_branch)
    result = app.run()
    if result:
        print(result)
