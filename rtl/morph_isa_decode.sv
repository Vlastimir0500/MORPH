module morph_isa_decode (
    input  logic [15:0] instr,
    output logic        drive_en,
    output logic        sample_en,
    output logic        wait_en,
    output logic        edge_en,
    output logic        shift_en,
    output logic        branch_en,
    output logic        loop_en,
    output logic        compare_en,
    output logic        trigger_en,
    output logic        expect_en,
    output logic [3:0]  pin_sel,
    output logic [7:0]  arg
);

always_comb begin
    drive_en   = 1'b0;
    sample_en  = 1'b0;
    wait_en    = 1'b0;
    edge_en    = 1'b0;
    shift_en   = 1'b0;
    branch_en  = 1'b0;
    loop_en    = 1'b0;
    compare_en = 1'b0;
    trigger_en = 1'b0;
    expect_en  = 1'b0;
    pin_sel    = instr[11:8];
    arg        = instr[7:0];

    case (instr[15:12])
        4'h1: drive_en   = 1'b1;
        4'h2: sample_en  = 1'b1;
        4'h3: wait_en    = 1'b1;
        4'h4: edge_en    = 1'b1;
        4'h5: shift_en   = 1'b1;
        4'h6: branch_en  = 1'b1;
        4'h7: loop_en    = 1'b1;
        4'h8: compare_en = 1'b1;
        4'h9: trigger_en = 1'b1;
        4'hA: expect_en  = 1'b1;
        default: begin end
    endcase
end

endmodule
