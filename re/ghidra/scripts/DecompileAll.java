// Writes the decompiled C of every function of the program (address order; thunks left out) to one file.
// Argument: OUT.c   (re/ghidra/refresh.sh -> re/decomp/zeus.c)
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class DecompileAll extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String target = getScriptArgs()[0];
        int done = 0;
        try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(Paths.get(target), StandardCharsets.UTF_8));
             Decomp dec = new Decomp(currentProgram, monitor)) {
            for (Function fn : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                if (fn.isThunk() || fn.isExternal()) continue;
                dec.write(out, fn);
                done++;
            }
        }
        println("DecompileAll: " + done + " functions -> " + target);
    }
}
