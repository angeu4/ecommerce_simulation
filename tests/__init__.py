from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression


@compiles(expression.Exists, 'sqlite')
def compile_exists_sqlite(element, compiler, **kw):
    """
    Compile an EXISTS expression construct for SQLite.
    
    This compiler is called for Exists constructs, and it is responsible
    for generating the appropriate SQL for the EXISTS construct.
    
    :param element: The EXISTS construct to compile.
    :param compiler: The compiler object which is being used to compile the
        construct.
    :param kw: Additional keyword arguments which may be used by the compiler.
    :return: The compiled SQL as a string.
    """
    
    text = compiler.process(element.select, **kw)
    return f"EXISTS {text}"
