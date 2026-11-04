// Decompiles the functions at the given addresses, first creating a function where Ghidra has none
// (works on a -readOnly project). Arguments: OUT.c HEXADDR...
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompAt extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] argv = getScriptArgs();
        try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(Paths.get(argv[0]), StandardCharsets.UTF_8));
             Decomp dec = new Decomp(currentProgram, monitor)) {
            for (String hex : java.util.Arrays.copyOfRange(argv, 1, argv.length)) {
                Address at = currentProgram.getAddressFactory().getDefaultAddressSpace()
                        .getAddress(Long.parseUnsignedLong(hex.replaceFirst("^0[xX]", ""), 16));
                Function fn = currentProgram.getFunctionManager().getFunctionAt(at);
                if (fn == null) {
                    disassemble(at);
                    fn = createFunction(at, null);
                }
                if (fn == null) {
                    out.print("// " + at + ": no function can be made here\n");
                } else {
                    dec.write(out, fn);
                }
            }
        }
    }
}
