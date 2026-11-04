// Applies our names and struct types to the program, then (optionally) re-exports decompiled C.
// Arguments: NAMES_DIR STRUCTS_DIR [MORE_NAMES_DIR...]
//   names files of all NAMES dirs are applied in file-name order (later files win), e.g. the fetched upstream
//   re/names/.upstream/00-arm64.tsv first and our zz-merged.tsv last
//   NAMES_DIR/*.tsv   : address<TAB>name<TAB>kind(function|data)<TAB>type<TAB>evidence...
//                       type (data only, optional): u8 i8 u16 i16 u32 i32 or a struct name, with
//                       an optional [count], e.g. Building[4000]
//   STRUCTS_DIR/*.tsv : struct<TAB>offset<TAB>type<TAB>name   (offset "size" gives total size)
// Lines starting with '#' and the header line (first column "address"/"struct") are skipped.
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class ApplyNames extends GhidraScript {
    private final Map<String, StructureDataType> structs = new LinkedHashMap<>();
    private DataTypeManager dtm;

    private List<String[]> rows(List<File> dirs, String header) throws Exception {
        List<String[]> out = new ArrayList<>();
        List<File> files = new ArrayList<>();
        for (File dir : dirs) {
            File[] in = dir.listFiles((d, n) -> n.endsWith(".tsv"));
            if (in != null) files.addAll(Arrays.asList(in));
        }
        files.sort(Comparator.comparing(File::getName));
        for (File f : files) {
            for (String line : Files.readAllLines(f.toPath(), StandardCharsets.UTF_8)) {
                if (line.isBlank() || line.startsWith("#")) continue;
                String[] p = line.split("\t", -1);
                if (p[0].equals(header)) continue;
                out.add(p);
            }
        }
        return out;
    }

    private DataType prim(String t) {
        switch (t) {
            case "u8": return ByteDataType.dataType;
            case "i8": return SignedByteDataType.dataType;
            case "u16": return WordDataType.dataType;
            case "i16": return ShortDataType.dataType;
            case "u32": return DWordDataType.dataType;
            case "i32": return IntegerDataType.dataType;
            case "char": return CharDataType.dataType;
            case "f32": return FloatDataType.dataType;
            case "f64": return DoubleDataType.dataType;
            case "ptr": return PointerDataType.dataType;
            default: return null;
        }
    }

    private DataType type(String spec) {
        spec = spec.trim();
        int count = 0;
        int b = spec.indexOf('[');
        if (b >= 0) {
            String n = spec.substring(b + 1, spec.indexOf(']')).trim();
            count = n.isEmpty() ? 0 : Integer.decode(n);
            spec = spec.substring(0, b);
        }
        DataType base = prim(spec);
        if (base == null) {
            StructureDataType s = structs.get(spec);
            if (s == null) throw new IllegalArgumentException("unknown type " + spec);
            base = dtm.resolve(s, DataTypeConflictHandler.REPLACE_HANDLER);
        }
        return count > 0 ? new ArrayDataType(base, count, base.getLength()) : base;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<File> namesDirs = new ArrayList<>();
        namesDirs.add(new File(args[0]));
        for (int i = 2; i < args.length; i++) namesDirs.add(new File(args[i]));
        List<File> structsDir = List.of(new File(args[1]));
        dtm = currentProgram.getDataTypeManager();

        // Structs: two passes (sizes first, then fields, so structs can nest in order of files).
        List<String[]> srows = rows(structsDir, "struct");
        for (String[] p : srows) {
            if (p[1].equals("size")) {
                structs.put(p[0], new StructureDataType(new CategoryPath("/zeus"), p[0],
                        Integer.decode(p[2])));
            }
        }
        int fields = 0;
        for (String[] p : srows) {
            if (p[1].equals("size")) continue;
            StructureDataType s = structs.get(p[0]);
            if (s == null) { printerr("struct without size: " + p[0]); continue; }
            try {
                DataType t = type(p[2]);
                s.replaceAtOffset(Integer.decode(p[1]), t, t.getLength(), p[3], null);
                fields++;
            } catch (Exception e) {
                printerr("field " + String.join(" ", p) + ": " + e.getMessage());
            }
        }
        for (StructureDataType s : structs.values()) {
            dtm.resolve(s, DataTypeConflictHandler.REPLACE_HANDLER);
        }

        int fn = 0, data = 0;
        for (String[] row : rows(namesDirs, "address")) {
            if (row.length < 2 || row[0].isEmpty()) continue;
            String label = row[1];
            boolean isData = row.length > 2 && row[2].equals("data");
            try {
                Address at = currentProgram.getAddressFactory().getDefaultAddressSpace()
                        .getAddress(Long.parseUnsignedLong(row[0].replaceFirst("^0[xX]", ""), 16));
                if (isData) {
                    String spec = row.length > 3 ? row[3] : "";
                    if (!spec.isBlank()) {   // typed global: make room, then lay the type down
                        DataType t = type(spec);
                        clearListing(at, at.add(t.getLength() - 1));
                        createData(at, t);
                    }
                    createLabel(at, label, true, SourceType.USER_DEFINED);
                    data++;
                    continue;
                }
                Function target = currentProgram.getFunctionManager().getFunctionAt(at);
                if (target == null) target = createFunction(at, label);
                if (target == null) continue;
                target.setName(label, SourceType.USER_DEFINED);
                fn++;
            } catch (Exception e) {
                printerr(row[0] + " " + label + ": " + e.getMessage());
            }
        }
        println(String.format("ApplyNames: %d structs, %d fields, %d functions, %d data",
                structs.size(), fields, fn, data));
    }
}
