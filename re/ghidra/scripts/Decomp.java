// Shared by DecompileAll.java and DecompAt.java: one decompiler session, one text block per function.
// Block format (tools/fn.py, tools/xref.py read the header):  // ===== NAME @ ADDRESS, SIZE bytes =====
// followed by Ghidra's C for the function, or "// decompile failed: REASON".
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import ghidra.util.task.TaskMonitor;

final class Decomp implements AutoCloseable {
    static final int SECONDS = 180;
    private final DecompInterface ifc = new DecompInterface();
    private final TaskMonitor monitor;

    Decomp(Program program, TaskMonitor monitor) {
        this.monitor = monitor;
        if (!ifc.openProgram(program)) {
            throw new IllegalStateException("decompiler: " + ifc.getLastMessage());
        }
    }

    void write(PrintWriter out, Function fn) {
        out.print("// ===== " + fn.getName() + " @ " + fn.getEntryPoint() + ", "
                + fn.getBody().getNumAddresses() + " bytes =====\n");
        DecompileResults res = ifc.decompileFunction(fn, SECONDS, monitor);
        if (res != null && res.decompileCompleted()) {
            out.print(res.getDecompiledFunction().getC());
        } else {
            out.print("// decompile failed: " + (res == null ? "no result" : res.getErrorMessage()));
        }
        out.print("\n");
    }

    @Override
    public void close() {
        ifc.dispose();
    }
}
