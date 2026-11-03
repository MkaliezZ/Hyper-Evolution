"""Frozen entry point; display actionable GUI startup errors without console secrets."""
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        from growth_local.__main__ import main
        main()
    except Exception as error:
        import sys
        if 'mcp' in __import__('pathlib').Path(sys.executable).stem.lower():
            raise
        import ctypes
        message = str(error) if isinstance(error, (ValueError, PermissionError)) else type(error).__name__
        ctypes.windll.user32.MessageBoxW(None,'超维伴学未能启动：'+message+'\n请保留原数据目录，并查看随包使用指南。','超维伴学',0x10)
        sys.exit(1)
